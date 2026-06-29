"""Embed published content into the vector store, scoped per user.

KIND_RESEARCH is a shared pool (no user_id payload).
KIND_POSTS and KIND_ARTICLES store the owning user_id in the payload — the
knowledge MCP filters on this so users can't query each other's content.
"""
import hashlib
import uuid
from typing import Any

import structlog

from database import AsyncSessionLocal
from models.embeddings import EmbeddingRecord
from services.ai.embeddings import get_active_embedder
from services.ai.vector_store import KIND_ARTICLES, KIND_INSPIRATION, KIND_POSTS, get_vector_store

logger = structlog.get_logger(__name__)


async def _record_provenance(
    user_id: uuid.UUID | None, doc_id: uuid.UUID, kind: str, text: str
) -> None:
    embedder = get_active_embedder()
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
    async with AsyncSessionLocal() as db:
        db.add(EmbeddingRecord(
            id=uuid.uuid4(),
            user_id=user_id,
            doc_id=doc_id,
            kind=kind,
            embedding_model_id=embedder.model_id,
            source_text_hash=text_hash,
        ))
        await db.commit()


async def index_published_post(
    user_id: uuid.UUID,
    post_id: uuid.UUID,
    content: str,
    domain: str,
    voice_style: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    try:
        store = get_vector_store()
        await store.upsert(
            kind=KIND_POSTS,
            doc_id=post_id,
            text=content,
            payload={
                "user_id": str(user_id),
                "domain": domain,
                "voice_style": voice_style,
                **(metadata or {}),
            },
        )
        await _record_provenance(user_id, post_id, "posts", content)
        logger.info("post_indexed", post_id=str(post_id), user_id=str(user_id))
    except Exception as exc:
        logger.error("post_index_failed", post_id=str(post_id), error=str(exc))


async def index_published_article(
    user_id: uuid.UUID,
    article_id: uuid.UUID,
    title: str,
    subtitle: str,
    body_markdown: str,
    domain: str,
    voice_style: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    text = f"# {title}\n\n{subtitle}\n\n{body_markdown}"
    try:
        store = get_vector_store()
        await store.upsert(
            kind=KIND_ARTICLES,
            doc_id=article_id,
            text=text,
            payload={
                "user_id": str(user_id),
                "title": title,
                "subtitle": subtitle,
                "domain": domain,
                "voice_style": voice_style,
                **(metadata or {}),
            },
        )
        await _record_provenance(user_id, article_id, "articles", text)
        logger.info("article_indexed", article_id=str(article_id), user_id=str(user_id))
    except Exception as exc:
        logger.error("article_index_failed", article_id=str(article_id), error=str(exc))


async def index_inspiration_post(
    post_id: uuid.UUID,
    hook_text: str,
    focus_area: str,
    domain: str,
    traction_score: float,
    pattern_tags: dict[str, Any] | None = None,
) -> None:
    try:
        store = get_vector_store()
        await store.upsert(
            kind=KIND_INSPIRATION,
            doc_id=post_id,
            text=hook_text,
            payload={
                "focus_area": focus_area,
                "domain": domain,
                "traction_score": traction_score,
                "hook_type": (pattern_tags or {}).get("hook_type", ""),
                "pattern_tags": pattern_tags or {},
            },
        )
        await _record_provenance(None, post_id, "inspiration", hook_text)
        logger.info("inspiration_indexed", post_id=str(post_id))
    except Exception as exc:
        logger.error("inspiration_index_failed", post_id=str(post_id), error=str(exc))
