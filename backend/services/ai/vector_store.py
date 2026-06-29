"""
Qdrant wrapper.

Collections are scoped by (kind, embedding_model_id). Switching the active embedding
model creates a new collection — old vectors remain queryable until `reembed_corpus`
migrates them. This avoids the "you changed the model, your DB is silently broken" trap.

Collection naming: `{kind}__{model_id_safe}` (e.g., `research__voyage_3`).
"""
import re
from typing import Any
from uuid import UUID

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qm

from config import get_settings
from services.ai.embeddings import EmbeddingProvider, get_active_embedder

logger = structlog.get_logger(__name__)

# Logical collection kinds. Add new ones here; never use string literals at call sites.
KIND_RESEARCH = "research"     # research_topics — for dedup + cache before re-fetching
KIND_POSTS = "posts"           # published LinkedIn posts — for voice consistency
KIND_ARTICLES = "articles"     # published Substack articles
KIND_SOURCES = "sources"       # extracted source text — for retrieving prior reads
KIND_INSPIRATION = "inspiration"  # harvested LinkedIn posts — style patterns only

_VALID_KINDS = {KIND_RESEARCH, KIND_POSTS, KIND_ARTICLES, KIND_SOURCES, KIND_INSPIRATION}


def _safe_model_id(model_id: str) -> str:
    """Qdrant collection names allow [A-Za-z0-9_-]. Replace dots and other punctuation."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", model_id)


class VectorStore:
    """Single-process Qdrant client wrapper. Construct via get_vector_store() to share
    the connection. Collections are created lazily on first upsert per kind."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
        )
        self._known_collections: set[str] = set()

    def collection_name(self, kind: str, embedder: EmbeddingProvider | None = None) -> str:
        if kind not in _VALID_KINDS:
            raise ValueError(f"Unknown collection kind: {kind}")
        embedder = embedder or get_active_embedder()
        return f"{kind}__{_safe_model_id(embedder.model_id)}"

    async def ensure_collection(self, kind: str, embedder: EmbeddingProvider | None = None) -> str:
        embedder = embedder or get_active_embedder()
        name = self.collection_name(kind, embedder)
        if name in self._known_collections:
            return name

        existing = await self._client.get_collections()
        if not any(c.name == name for c in existing.collections):
            await self._client.create_collection(
                collection_name=name,
                vectors_config=qm.VectorParams(
                    size=embedder.dimensions,
                    distance=qm.Distance.COSINE,
                ),
            )
            logger.info(
                "qdrant_collection_created",
                name=name,
                dim=embedder.dimensions,
                model=embedder.model_id,
            )

        self._known_collections.add(name)
        return name

    async def upsert(
        self,
        kind: str,
        doc_id: UUID | str,
        text: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Embed `text` with the active provider and upsert into the kind's collection.
        `doc_id` should be the canonical Postgres row UUID so re-embed jobs can find it.
        """
        embedder = get_active_embedder()
        collection = await self.ensure_collection(kind, embedder)
        vectors = await embedder.embed([text], input_type="document")
        await self._client.upsert(
            collection_name=collection,
            points=[
                qm.PointStruct(
                    id=str(doc_id),
                    vector=vectors[0],
                    payload={**(payload or {}), "text": text},
                )
            ],
        )

    async def upsert_batch(
        self,
        kind: str,
        items: list[tuple[UUID | str, str, dict[str, Any] | None]],
    ) -> None:
        """Bulk upsert. Embeds all texts in one provider call — much cheaper for re-embed jobs."""
        if not items:
            return
        embedder = get_active_embedder()
        collection = await self.ensure_collection(kind, embedder)
        texts = [text for _, text, _ in items]
        vectors = await embedder.embed(texts, input_type="document")
        await self._client.upsert(
            collection_name=collection,
            points=[
                qm.PointStruct(
                    id=str(doc_id),
                    vector=vec,
                    payload={**(payload or {}), "text": text},
                )
                for (doc_id, text, payload), vec in zip(items, vectors)
            ],
        )

    async def search(
        self,
        kind: str,
        query_text: str,
        limit: int = 5,
        score_threshold: float | None = None,
        filter_payload: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search. Returns list of {id, score, payload}.

        `score_threshold` defaults to settings.vector_similarity_threshold. Pass 0 to
        disable filtering and inspect raw scores during tuning.
        """
        settings = get_settings()
        threshold = (
            score_threshold if score_threshold is not None else settings.vector_similarity_threshold
        )

        embedder = get_active_embedder()
        collection = await self.ensure_collection(kind, embedder)
        query_vec = (await embedder.embed([query_text], input_type="query"))[0]

        qdrant_filter = None
        if filter_payload:
            qdrant_filter = qm.Filter(
                must=[
                    qm.FieldCondition(key=k, match=qm.MatchValue(value=v))
                    for k, v in filter_payload.items()
                ]
            )

        results = await self._client.search(
            collection_name=collection,
            query_vector=query_vec,
            limit=limit,
            score_threshold=threshold,
            query_filter=qdrant_filter,
        )
        return [
            {"id": str(r.id), "score": r.score, "payload": r.payload or {}}
            for r in results
        ]

    async def delete(self, kind: str, doc_id: UUID | str) -> None:
        embedder = get_active_embedder()
        collection = await self.ensure_collection(kind, embedder)
        await self._client.delete(
            collection_name=collection,
            points_selector=qm.PointIdsList(points=[str(doc_id)]),
        )

    async def close(self) -> None:
        await self._client.close()


_singleton: VectorStore | None = None


def get_vector_store() -> VectorStore:
    """Process-wide singleton. Tests can monkeypatch this."""
    global _singleton
    if _singleton is None:
        _singleton = VectorStore()
    return _singleton
