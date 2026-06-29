"""Distill style patterns from harvested LinkedIn posts."""
from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import select

from database import AsyncSessionLocal
from models.brain import InspirationPost
from services.ai.ingestion import index_inspiration_post
from services.content.prompts import (
    STYLE_PATTERN_EXTRACTION_PROMPT,
    _BANNED_PHRASE_LIST,
)

logger = structlog.get_logger(__name__)


async def extract_patterns_for_post(post_id: uuid.UUID) -> dict[str, Any] | None:
    async with AsyncSessionLocal() as db:
        post = (
            await db.execute(select(InspirationPost).where(InspirationPost.id == post_id))
        ).scalar_one_or_none()
        if not post:
            return None
        text = post.full_text or post.hook_text
        if not text:
            post.status = "archived"
            await db.commit()
            return None

        from services.ai.claude_client import generate_json

        prompt = STYLE_PATTERN_EXTRACTION_PROMPT.format(
            banned_phrases=_BANNED_PHRASE_LIST,
            post_text=text[:3500],
        )
        try:
            patterns = await generate_json(
                task="style_pattern_extraction",
                system="Return only valid JSON.",
                user=prompt,
                max_tokens=512,
            )
        except Exception as exc:
            logger.warning("pattern_extraction_failed", post_id=str(post_id), error=str(exc))
            return None

        post.pattern_tags = patterns
        post.status = "processed"
        await db.commit()

    await index_inspiration_post(
        post_id=post_id,
        hook_text=post.hook_text,
        focus_area=post.focus_area,
        domain=post.domain,
        traction_score=post.traction_score,
        pattern_tags=patterns,
    )
    logger.info("pattern_extracted", post_id=str(post_id), hook_type=patterns.get("hook_type"))
    return patterns


async def process_pending() -> dict[str, int]:
    async with AsyncSessionLocal() as db:
        pending = (
            await db.execute(
                select(InspirationPost).where(InspirationPost.status == "new").limit(10)
            )
        ).scalars().all()
        ids = [p.id for p in pending]

    processed = 0
    for pid in ids:
        if await extract_patterns_for_post(pid):
            processed += 1
    return {"processed": processed}
