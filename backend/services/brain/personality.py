"""Per-user voice profile synthesis and overlay."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import desc, select

from database import AsyncSessionLocal
from models.brain import UserVoiceProfile
from models.content import Post
from models.user import User
from services.brain.queries import default_focus_areas
from services.content.prompts import USER_PERSONALITY_OVERLAY, USER_PERSONALITY_SYNTHESIS_PROMPT
from services.content.tone import load_tone_preferences

logger = structlog.get_logger(__name__)


async def get_or_create_profile(user_id: UUID) -> UserVoiceProfile:
    async with AsyncSessionLocal() as db:
        profile = (
            await db.execute(
                select(UserVoiceProfile).where(UserVoiceProfile.user_id == user_id)
            )
        ).scalar_one_or_none()
        if profile:
            return profile
        profile = UserVoiceProfile(
            user_id=user_id,
            focus_areas=default_focus_areas(),
        )
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
        return profile


async def update_profile_bio(
    user_id: UUID,
    bio_context: str | None,
    focus_areas: list[str] | None,
) -> UserVoiceProfile:
    async with AsyncSessionLocal() as db:
        profile = (
            await db.execute(
                select(UserVoiceProfile).where(UserVoiceProfile.user_id == user_id)
            )
        ).scalar_one_or_none()
        if not profile:
            profile = UserVoiceProfile(user_id=user_id, focus_areas=default_focus_areas())
            db.add(profile)
        if bio_context is not None:
            profile.bio_context = bio_context.strip() or None
        if focus_areas is not None and focus_areas:
            profile.focus_areas = focus_areas
        await db.commit()
        await db.refresh(profile)
        return profile


async def get_personality_overlay(user_id: UUID) -> str:
    async with AsyncSessionLocal() as db:
        profile = (
            await db.execute(
                select(UserVoiceProfile).where(UserVoiceProfile.user_id == user_id)
            )
        ).scalar_one_or_none()

    if not profile or not profile.personality_summary:
        return ""

    phrases = profile.sample_phrases or []
    affinites = profile.hook_affinites or {}
    return USER_PERSONALITY_OVERLAY.format(
        personality_summary=profile.personality_summary,
        sample_phrases="\n".join(f'- "{p}"' for p in phrases[:10]) or "(none yet)",
        hook_affinites=json.dumps(affinites, indent=2),
    )


async def refresh_profile(user_id: UUID) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        posts = (
            await db.execute(
                select(Post)
                .where(Post.user_id == user_id, Post.status == "published")
                .order_by(desc(Post.published_at))
                .limit(30)
            )
        ).scalars().all()

    def traction(p: Post) -> int:
        m = p.metrics or {}
        return int(m.get("engagement_total", 0) or m.get("likes", 0))

    top_posts = sorted(posts, key=traction, reverse=True)[:10]
    if len(top_posts) < 1:
        logger.info("personality_refresh_skipped", user_id=str(user_id), reason="no_posts")
        return {"status": "skipped", "reason": "no_posts"}

    tone = await load_tone_preferences(user_id)
    profile = await get_or_create_profile(user_id)
    posts_sample = "\n\n---\n\n".join(
        f"Engagement: {traction(p)}\n{p.content[:1200]}" for p in top_posts
    )

    from services.ai.claude_client import generate_json

    prompt = USER_PERSONALITY_SYNTHESIS_PROMPT.format(
        bio_context=profile.bio_context or "",
        tone_preferences=json.dumps(tone),
        posts_sample=posts_sample[:8000],
    )
    try:
        data = await generate_json(
            task="personality_synthesis",
            system="Return only valid JSON.",
            user=prompt,
            max_tokens=1500,
        )
    except Exception as exc:
        logger.error("personality_synthesis_failed", user_id=str(user_id), error=str(exc))
        return {"status": "error", "error": str(exc)}

    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(UserVoiceProfile).where(UserVoiceProfile.user_id == user_id)
            )
        ).scalar_one_or_none()
        if not row:
            row = UserVoiceProfile(user_id=user_id, focus_areas=default_focus_areas())
            db.add(row)
        row.personality_summary = data.get("personality_summary", "")
        row.hook_affinites = data.get("hook_affinites", {})
        row.sample_phrases = data.get("sample_phrases", [])
        row.structural_preferences = data.get("structural_preferences", {})
        await db.commit()

    logger.info("personality_refreshed", user_id=str(user_id))
    return {"status": "complete", "user_id": str(user_id)}


async def refresh_all_profiles() -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        users = (await db.execute(select(User).where(User.is_active.is_(True)))).scalars().all()

    results = []
    for u in users:
        try:
            results.append(await refresh_profile(u.id))
        except Exception as exc:
            logger.error("personality_refresh_user_failed", user_id=str(u.id), error=str(exc))
            results.append({"user_id": str(u.id), "status": "error", "error": str(exc)})
    return {"users": results}


async def get_profile_dict(user_id: UUID) -> dict[str, Any]:
    profile = await get_or_create_profile(user_id)
    return {
        "user_id": str(profile.user_id),
        "personality_summary": profile.personality_summary,
        "hook_affinites": profile.hook_affinites,
        "structural_preferences": profile.structural_preferences,
        "sample_phrases": profile.sample_phrases,
        "focus_areas": profile.focus_areas or default_focus_areas(),
        "bio_context": profile.bio_context,
        "insights": profile.insights,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }
