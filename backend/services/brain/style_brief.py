"""Build style briefs from inspiration corpus for content generation."""
from __future__ import annotations

import json
from typing import Any

import structlog
from sqlalchemy import desc, select

from database import AsyncSessionLocal
from models.brain import InspirationPost

logger = structlog.get_logger(__name__)


async def get_style_brief(focus_area: str, domain: str, limit: int = 2) -> str:
    async with AsyncSessionLocal() as db:
        posts = (
            await db.execute(
                select(InspirationPost)
                .where(
                    InspirationPost.status == "processed",
                    InspirationPost.domain == domain,
                )
                .order_by(desc(InspirationPost.traction_score))
                .limit(limit * 3)
            )
        ).scalars().all()

    matching = [p for p in posts if p.focus_area == focus_area or not focus_area][:limit]
    if not matching:
        matching = posts[:limit]

    if not matching:
        return ""

    lines: list[str] = []
    for p in matching:
        tags = p.pattern_tags or {}
        lines.append(
            f"- hook_type={tags.get('hook_type', 'unknown')}, "
            f"structure={tags.get('structure', 'unknown')}, "
            f"rhythm={tags.get('paragraph_rhythm', 'mixed')}, "
            f"cta={tags.get('cta_style', 'none')}"
        )
    return "\n".join(lines)


async def list_inspiration(
    domain: str | None = None,
    min_traction: float = 0.0,
    limit: int = 20,
) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as db:
        q = select(InspirationPost).where(InspirationPost.traction_score >= min_traction)
        if domain:
            q = q.where(InspirationPost.domain == domain)
        q = q.order_by(desc(InspirationPost.traction_score)).limit(limit)
        posts = (await db.execute(q)).scalars().all()

    return [
        {
            "id": str(p.id),
            "url": p.url,
            "author_handle": p.author_handle,
            "hook_text": p.hook_text[:120],
            "focus_area": p.focus_area,
            "domain": p.domain,
            "traction_score": p.traction_score,
            "pattern_tags": p.pattern_tags,
            "harvested_at": p.harvested_at.isoformat(),
            "status": p.status,
        }
        for p in posts
    ]
