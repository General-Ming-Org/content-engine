"""
Content Engine Knowledge MCP server — per-user scoped.

Auth model:
  - Every request must include `Authorization: Bearer <token>`.
  - The token is a personal MCP token issued via POST /api/credentials/mcp-token.
  - We hash-lookup the token and resolve the caller's user_id.
  - All searches are scoped to that user_id via Qdrant payload filter.

KIND_RESEARCH stays cross-user (shared pool) but search_research is still
authenticated — anonymous reads aren't supported.

Transport: streamable HTTP on port 8002.
"""
import hashlib
import os
from contextvars import ContextVar
from typing import Any
from uuid import UUID

import structlog
from mcp.server.fastmcp import FastMCP
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from database import AsyncSessionLocal
from models.research import ResearchTopic
from services.ai.vector_store import (
    KIND_ARTICLES,
    KIND_POSTS,
    KIND_RESEARCH,
    get_vector_store,
)
from services.credentials.store import find_user_by_mcp_token_hash

logger = structlog.get_logger(__name__)

# Per-request user context. Set by AuthMiddleware before each tool call.
_current_user: ContextVar[UUID | None] = ContextVar("current_user", default=None)


def _require_user() -> UUID:
    user_id = _current_user.get()
    if user_id is None:
        raise PermissionError("Unauthenticated MCP request")
    return user_id


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return JSONResponse({"error": "Missing bearer token"}, status_code=401)

        token = auth.split(" ", 1)[1].strip()
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        user_id = await find_user_by_mcp_token_hash(token_hash)
        if user_id is None:
            return JSONResponse({"error": "Invalid token"}, status_code=401)

        token_obj = _current_user.set(user_id)
        try:
            return await call_next(request)
        finally:
            _current_user.reset(token_obj)


mcp = FastMCP(
    "content-engine-knowledge",
    instructions=(
        "Tools for querying YOUR accumulated content (research, LinkedIn posts, Substack articles). "
        "All queries are auto-scoped to the authenticated user. Use search_* tools to find prior "
        "work on a topic; use list_recent_topics to see what the engine is tracking for you."
    ),
    # FastMCP reads `host`/`port` from constructor settings; `mcp.run()` no longer
    # accepts them as kwargs as of mcp >= ~1.6.
    host=os.getenv("MCP_HOST", "0.0.0.0"),
    port=int(os.getenv("MCP_PORT", "8002")),
)


@mcp.tool()
async def search_research(query: str, limit: int = 5, domain: str | None = None) -> list[dict[str, Any]]:
    """Search the shared research pool by semantic similarity.

    Args:
        query: Natural language query — the system embeds and ranks.
        limit: Max results (1-20).
        domain: Optional filter — one of ai_ml, software_eng, sre_infra, data_eng.
    """
    _require_user()
    store = get_vector_store()
    hits = await store.search(
        kind=KIND_RESEARCH,
        query_text=query,
        limit=max(1, min(limit, 20)),
        score_threshold=0.0,
        filter_payload={"domain": domain} if domain else None,
    )
    return [
        {
            "id": h["id"],
            "score": round(h["score"], 3),
            "title": h["payload"].get("title"),
            "summary": h["payload"].get("summary"),
            "domain": h["payload"].get("domain"),
        }
        for h in hits
    ]


@mcp.tool()
async def search_posts(query: str, limit: int = 5, domain: str | None = None) -> list[dict[str, Any]]:
    """Search YOUR published LinkedIn posts."""
    user_id = _require_user()
    store = get_vector_store()
    filter_payload: dict[str, Any] = {"user_id": str(user_id)}
    if domain:
        filter_payload["domain"] = domain

    hits = await store.search(
        kind=KIND_POSTS,
        query_text=query,
        limit=max(1, min(limit, 20)),
        score_threshold=0.0,
        filter_payload=filter_payload,
    )
    return [
        {
            "id": h["id"],
            "score": round(h["score"], 3),
            "domain": h["payload"].get("domain"),
            "voice_style": h["payload"].get("voice_style"),
            "excerpt": (h["payload"].get("text") or "")[:400],
        }
        for h in hits
    ]


@mcp.tool()
async def search_articles(query: str, limit: int = 5, domain: str | None = None) -> list[dict[str, Any]]:
    """Search YOUR published Substack articles."""
    user_id = _require_user()
    store = get_vector_store()
    filter_payload: dict[str, Any] = {"user_id": str(user_id)}
    if domain:
        filter_payload["domain"] = domain

    hits = await store.search(
        kind=KIND_ARTICLES,
        query_text=query,
        limit=max(1, min(limit, 20)),
        score_threshold=0.0,
        filter_payload=filter_payload,
    )
    return [
        {
            "id": h["id"],
            "score": round(h["score"], 3),
            "title": h["payload"].get("title"),
            "subtitle": h["payload"].get("subtitle"),
            "domain": h["payload"].get("domain"),
            "voice_style": h["payload"].get("voice_style"),
            "excerpt": (h["payload"].get("text") or "")[:600],
        }
        for h in hits
    ]


@mcp.tool()
async def get_research_topic(topic_id: str) -> dict[str, Any] | None:
    """Fetch a single research topic from the shared pool."""
    _require_user()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ResearchTopic).where(ResearchTopic.id == topic_id))
        topic = result.scalar_one_or_none()
        if not topic:
            return None
        return {
            "id": str(topic.id),
            "title": topic.title,
            "summary": topic.summary,
            "domain": topic.domain,
            "relevance_score": topic.relevance_score,
            "status": topic.status,
            "sources": topic.sources,
            "created_at": topic.created_at.isoformat() if topic.created_at else None,
        }


@mcp.tool()
async def list_recent_topics(limit: int = 10, domain: str | None = None) -> list[dict[str, Any]]:
    """List the most recent research topics in the shared pool."""
    _require_user()
    async with AsyncSessionLocal() as db:
        stmt = select(ResearchTopic).order_by(ResearchTopic.created_at.desc()).limit(
            max(1, min(limit, 50))
        )
        if domain:
            stmt = stmt.where(ResearchTopic.domain == domain)
        result = await db.execute(stmt)
        topics = result.scalars().all()
    return [
        {
            "id": str(t.id),
            "title": t.title,
            "domain": t.domain,
            "status": t.status,
            "score": t.relevance_score,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in topics
    ]


def _attach_auth_middleware() -> None:
    """FastMCP exposes the underlying Starlette app via `.streamable_http_app()`.
    We wrap that with our auth middleware before serving."""
    original_factory = mcp.streamable_http_app

    def wrapped() -> Any:
        app = original_factory()
        app.add_middleware(AuthMiddleware)
        return app

    mcp.streamable_http_app = wrapped  # type: ignore[assignment]


if __name__ == "__main__":
    _attach_auth_middleware()
    logger.info(
        "knowledge_mcp_starting",
        host=mcp.settings.host,
        port=mcp.settings.port,
    )
    mcp.run(transport="streamable-http")
