"""
Re-embed the existing corpus when the active embedding model changes.

For each (kind, doc), we check if an EmbeddingRecord exists for the current model.
If not, we fetch the canonical text from Postgres, embed in batches, and upsert
into the current Qdrant collection (which is created lazily on first write).

Runs as a Celery task. Safe to run repeatedly — it's a no-op when everything
is already embedded with the active model.
"""
import hashlib
import uuid
from typing import Any

import structlog
from sqlalchemy import select

from database import AsyncSessionLocal
from models.content import Article, Post
from models.embeddings import EmbeddingRecord
from models.research import ResearchTopic
from services.ai.embeddings import get_active_embedder
from services.ai.vector_store import (
    KIND_ARTICLES,
    KIND_POSTS,
    KIND_RESEARCH,
    get_vector_store,
)

logger = structlog.get_logger(__name__)

BATCH_SIZE = 32


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


async def _find_unembedded_ids(kind: str, model_id: str, candidate_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """Return the subset of candidate_ids that don't have an EmbeddingRecord
    for the given (kind, model_id) pair."""
    if not candidate_ids:
        return set()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(EmbeddingRecord.doc_id).where(
                EmbeddingRecord.kind == kind,
                EmbeddingRecord.embedding_model_id == model_id,
                EmbeddingRecord.doc_id.in_(candidate_ids),
            )
        )
        already = {row[0] for row in result.all()}
    return set(candidate_ids) - already


async def _reembed_research() -> dict[str, int]:
    embedder = get_active_embedder()
    store = get_vector_store()

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ResearchTopic.id, ResearchTopic.title, ResearchTopic.summary, ResearchTopic.domain))
        rows = result.all()

    by_id = {r[0]: r for r in rows}
    todo = await _find_unembedded_ids("research", embedder.model_id, list(by_id.keys()))
    if not todo:
        return {"embedded": 0, "total": len(rows)}

    embedded = 0
    items = list(todo)
    for i in range(0, len(items), BATCH_SIZE):
        chunk = items[i : i + BATCH_SIZE]
        batch_items = []
        records = []
        for doc_id in chunk:
            _, title, summary, domain = by_id[doc_id]
            text = f"{title}\n\n{summary or ''}"
            batch_items.append((doc_id, text, {"title": title, "summary": summary, "domain": domain}))
            records.append((doc_id, text))

        await store.upsert_batch(KIND_RESEARCH, batch_items)

        async with AsyncSessionLocal() as db:
            for doc_id, text in records:
                db.add(EmbeddingRecord(
                    id=uuid.uuid4(),
                    doc_id=doc_id,
                    kind="research",
                    embedding_model_id=embedder.model_id,
                    source_text_hash=_hash(text),
                ))
            await db.commit()
        embedded += len(chunk)
        logger.info("reembed_progress", kind="research", embedded=embedded, total=len(items))

    return {"embedded": embedded, "total": len(rows)}


async def _reembed_posts() -> dict[str, int]:
    embedder = get_active_embedder()
    store = get_vector_store()

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Post.id, Post.content, Post.voice_style).where(Post.status == "published")
        )
        rows = result.all()

    by_id = {r[0]: r for r in rows}
    todo = await _find_unembedded_ids("posts", embedder.model_id, list(by_id.keys()))
    if not todo:
        return {"embedded": 0, "total": len(rows)}

    embedded = 0
    items = list(todo)
    for i in range(0, len(items), BATCH_SIZE):
        chunk = items[i : i + BATCH_SIZE]
        batch_items = []
        records = []
        for doc_id in chunk:
            _, content, voice_style = by_id[doc_id]
            batch_items.append((doc_id, content, {"voice_style": voice_style, "domain": "software_eng"}))
            records.append((doc_id, content))

        await store.upsert_batch(KIND_POSTS, batch_items)

        async with AsyncSessionLocal() as db:
            for doc_id, text in records:
                db.add(EmbeddingRecord(
                    id=uuid.uuid4(),
                    doc_id=doc_id,
                    kind="posts",
                    embedding_model_id=embedder.model_id,
                    source_text_hash=_hash(text),
                ))
            await db.commit()
        embedded += len(chunk)

    return {"embedded": embedded, "total": len(rows)}


async def _reembed_articles() -> dict[str, int]:
    embedder = get_active_embedder()
    store = get_vector_store()

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Article.id, Article.title, Article.subtitle, Article.body_markdown, Article.voice_style)
            .where(Article.status == "published")
        )
        rows = result.all()

    by_id = {r[0]: r for r in rows}
    todo = await _find_unembedded_ids("articles", embedder.model_id, list(by_id.keys()))
    if not todo:
        return {"embedded": 0, "total": len(rows)}

    embedded = 0
    items = list(todo)
    for i in range(0, len(items), BATCH_SIZE):
        chunk = items[i : i + BATCH_SIZE]
        batch_items = []
        records = []
        for doc_id in chunk:
            _, title, subtitle, body, voice_style = by_id[doc_id]
            text = f"# {title}\n\n{subtitle or ''}\n\n{body}"
            batch_items.append((doc_id, text, {"title": title, "subtitle": subtitle, "voice_style": voice_style}))
            records.append((doc_id, text))

        await store.upsert_batch(KIND_ARTICLES, batch_items)

        async with AsyncSessionLocal() as db:
            for doc_id, text in records:
                db.add(EmbeddingRecord(
                    id=uuid.uuid4(),
                    doc_id=doc_id,
                    kind="articles",
                    embedding_model_id=embedder.model_id,
                    source_text_hash=_hash(text),
                ))
            await db.commit()
        embedded += len(chunk)

    return {"embedded": embedded, "total": len(rows)}


async def reembed_corpus() -> dict[str, Any]:
    """Re-embed everything that doesn't have a record for the active model.
    Returns per-kind counts. Idempotent."""
    embedder = get_active_embedder()
    logger.info("reembed_corpus_start", model=embedder.model_id, dim=embedder.dimensions)

    research = await _reembed_research()
    posts = await _reembed_posts()
    articles = await _reembed_articles()

    return {
        "active_model": embedder.model_id,
        "research": research,
        "posts": posts,
        "articles": articles,
    }
