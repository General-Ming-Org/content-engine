"""Topic scoring, dedup (via vector DB), and DB persistence.

Dedup is now semantic — we ask Qdrant for the nearest neighbor and reject if it's
above the configured similarity threshold. The old n-gram heuristic is kept as a
zero-API fallback when the vector store is unreachable.
"""
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import AsyncSessionLocal
from models.embeddings import EmbeddingRecord
from models.research import ResearchTopic
from services.ai.embeddings import get_active_embedder
from services.ai.vector_store import KIND_RESEARCH, get_vector_store
from services.research.dedupe import is_duplicate_in_db
from services.research.sanitize import sanitize_payload

logger = structlog.get_logger(__name__)


def _compute_score(enriched: dict[str, Any]) -> float:
    synthesis = enriched.get("synthesis", {})
    confidence = synthesis.get("confidence", 5) / 10.0
    key_facts = synthesis.get("key_facts", [])
    signal = min(len(key_facts) / 5.0, 1.0)
    trade_offs = synthesis.get("trade_offs", "")
    audience_fit = 1.0 if trade_offs else 0.6
    recency = 1.0
    return round(0.25 * recency + 0.25 * signal + 0.25 * confidence + 0.25 * audience_fit, 3)


def _ngram_similarity(a: str, b: str) -> float:
    """Cheap fallback when the vector store is unreachable."""
    def ngrams(text: str, n: int = 3) -> set[str]:
        text = text.lower()
        return {text[i:i+n] for i in range(len(text) - n + 1)}
    a_set, b_set = ngrams(a), ngrams(b)
    if not a_set or not b_set:
        return 0.0
    return len(a_set & b_set) / len(a_set | b_set)


async def _is_duplicate_semantic(title: str, summary: str) -> bool:
    """Vector search against existing research topics. Returns True on near-match."""
    settings = get_settings()
    try:
        store = get_vector_store()
        hits = await store.search(
            kind=KIND_RESEARCH,
            query_text=f"{title}\n\n{summary}",
            limit=1,
            score_threshold=settings.vector_similarity_threshold,
        )
        if hits:
            logger.debug("duplicate_topic_semantic", title=title, score=hits[0]["score"])
            return True
    except Exception as exc:
        logger.warning("vector_dedup_failed_falling_back", error=str(exc))
        return await _is_duplicate_ngram_fallback(title, summary)
    return False


async def _is_duplicate_ngram_fallback(title: str, summary: str) -> bool:
    async with AsyncSessionLocal() as db:
        recent = (
            await db.execute(
                select(ResearchTopic)
                .where(ResearchTopic.status.in_(["new", "assigned"]))
                .order_by(ResearchTopic.created_at.desc())
                .limit(200)
            )
        ).scalars().all()

    candidate = f"{title} {summary}"
    for existing in recent:
        existing_text = f"{existing.title} {existing.summary or ''}"
        if _ngram_similarity(candidate, existing_text) >= 0.85:
            return True
    return False


async def _embed_and_record(topic: ResearchTopic, synthesis: dict[str, Any]) -> None:
    """Push the topic into Qdrant and record provenance in embedding_records."""
    embedder = get_active_embedder()
    store = get_vector_store()
    text = f"{topic.title}\n\n{topic.summary or ''}"
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]

    await store.upsert(
        kind=KIND_RESEARCH,
        doc_id=topic.id,
        text=text,
        payload={
            "title": topic.title,
            "summary": topic.summary,
            "domain": topic.domain,
            "synthesis": synthesis,
            "sources": topic.sources,
        },
    )

    async with AsyncSessionLocal() as db:
        db.add(EmbeddingRecord(
            id=uuid.uuid4(),
            doc_id=topic.id,
            kind="research",
            embedding_model_id=embedder.model_id,
            source_text_hash=text_hash,
        ))
        await db.commit()


async def score_and_store(enriched: dict[str, Any]) -> ResearchTopic | None:
    """Score, dedup (semantic), persist to Postgres, and index in the vector store."""
    score = _compute_score(enriched)
    synthesis = enriched.get("synthesis", {})
    primary_url = None
    sources = enriched.get("sources")
    if isinstance(sources, list) and sources and isinstance(sources[0], dict):
        primary_url = sources[0].get("url")

    if await is_duplicate_in_db(
        enriched["title"],
        url=primary_url,
        sources=sources,
    ):
        logger.info(
            "research_topic_skipped",
            title=enriched["title"],
            reason="duplicate_db",
        )
        return None

    if await _is_duplicate_semantic(enriched["title"], enriched["summary"]):
        logger.info(
            "research_topic_skipped",
            title=enriched["title"],
            reason="duplicate",
        )
        return None

    clean = sanitize_payload(enriched)
    async with AsyncSessionLocal() as db:
        topic = ResearchTopic(
            id=uuid.uuid4(),
            title=clean["title"],
            summary=clean["summary"],
            sources=clean.get("sources"),
            domain=clean["domain"],
            relevance_score=score,
            status="new",
            created_at=datetime.now(timezone.utc),
        )
        db.add(topic)
        await db.commit()
        await db.refresh(topic)
        logger.info("topic_stored", title=topic.title, score=score, domain=topic.domain)

    try:
        await _embed_and_record(topic, synthesis)
    except Exception as exc:
        logger.error("topic_embedding_failed", topic_id=str(topic.id), error=str(exc))

    return topic


async def store_stance(stance: dict[str, Any]) -> ResearchTopic | None:
    """Persist a gated stance as a research topic. Scored by debatability, not key_facts."""
    from services.research.queries import focus_area_to_domain

    thesis = stance["thesis"]
    focus_area = stance.get("focus_area") or stance.get("topic") or ""
    domain = focus_area_to_domain(focus_area)
    score = round(float(stance.get("debatability_score", 0)) / 10.0, 3)

    if await is_duplicate_in_db(thesis, url=stance.get("source_url")):
        logger.info("stance_skipped", reason="duplicate_db", thesis=thesis[:80])
        return None

    if await _is_duplicate_semantic(thesis, thesis):
        logger.info("stance_skipped", reason="duplicate_semantic", thesis=thesis[:80])
        return None

    sources = [{
        "url": stance.get("source_url", ""),
        "title": stance.get("topic", thesis[:80]),
        "stance": stance,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }]

    async with AsyncSessionLocal() as db:
        topic = ResearchTopic(
            id=uuid.uuid4(),
            title=thesis[:200],
            summary=thesis,
            sources=sources,
            domain=domain,
            relevance_score=score,
            status="new",
            created_at=datetime.now(timezone.utc),
        )
        db.add(topic)
        await db.commit()
        await db.refresh(topic)
        logger.info("stance_stored", thesis=thesis[:80], score=score, domain=domain)

    try:
        await _embed_and_record(topic, {"stance": stance, "source": "opinion_mining"})
    except Exception as exc:
        logger.error("stance_embedding_failed", topic_id=str(topic.id), error=str(exc))

    return topic
