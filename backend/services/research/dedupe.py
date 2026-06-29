"""Deduplicate research topics by normalized title and source URL."""
from __future__ import annotations

import re
import uuid
from typing import Any
from urllib.parse import urlparse, urlunparse

import structlog
from sqlalchemy import select

from database import AsyncSessionLocal
from models.research import ResearchTopic

logger = structlog.get_logger(__name__)

_TITLE_PREFIX = re.compile(r"^\s*\[(?:pdf|article)\]\s*", re.IGNORECASE)


def normalize_title(title: str) -> str:
    t = _TITLE_PREFIX.sub("", title or "")
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t


def canonical_url(url: str | None) -> str | None:
    if not url or not url.strip():
        return None
    try:
        parsed = urlparse(url.strip())
        if not parsed.scheme or not parsed.netloc:
            return url.strip().lower()
        path = parsed.path.rstrip("/") or "/"
        return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", "", ""))
    except Exception:
        return url.strip().lower()


def urls_from_sources(sources: Any) -> set[str]:
    out: set[str] = set()
    if not isinstance(sources, list):
        return out
    for item in sources:
        if isinstance(item, dict):
            u = canonical_url(item.get("url"))
            if u:
                out.add(u)
    return out


async def is_duplicate_in_db(
    title: str,
    user_id: uuid.UUID,
    *,
    url: str | None = None,
    sources: Any = None,
) -> bool:
    """True if this user already has an active topic with the same title or URL."""
    norm_title = normalize_title(title)
    candidate_urls = set()
    if url:
        cu = canonical_url(url)
        if cu:
            candidate_urls.add(cu)
    candidate_urls |= urls_from_sources(sources)

    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(ResearchTopic).where(
                    ResearchTopic.user_id == user_id,
                    ResearchTopic.status.in_(["new", "assigned"]),
                )
            )
        ).scalars().all()

    for row in rows:
        if normalize_title(row.title) == norm_title:
            return True
        if candidate_urls and candidate_urls & urls_from_sources(row.sources):
            return True
    return False


async def archive_duplicate_topics(user_id: uuid.UUID) -> int:
    """Archive extra copies of the same topic for one user (keeps highest relevance_score)."""
    archived = 0
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(ResearchTopic).where(
                    ResearchTopic.user_id == user_id,
                    ResearchTopic.status == "new",
                )
            )
        ).scalars().all()

        by_title: dict[str, list[ResearchTopic]] = {}
        for row in rows:
            key = normalize_title(row.title)
            by_title.setdefault(key, []).append(row)

        for group in by_title.values():
            if len(group) < 2:
                continue
            group.sort(
                key=lambda t: (t.relevance_score or 0, t.created_at),
                reverse=True,
            )
            for duplicate in group[1:]:
                duplicate.status = "archived"
                archived += 1
        if archived:
            await db.commit()
            logger.info("research_duplicates_archived", count=archived)
    return archived
