"""Performance feedback loop — winners inform profiles and research boosts."""
from __future__ import annotations

from collections import Counter
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import desc, select

from database import AsyncSessionLocal
from models.brain import UserVoiceProfile
from models.content import Post
from models.research import ResearchTopic
from models.user import User

logger = structlog.get_logger(__name__)


def _traction(post: Post) -> int:
    m = post.metrics or {}
    return int(m.get("engagement_total", 0) or m.get("likes", 0))


async def compute_winning_patterns(user_id: UUID) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        posts = (
            await db.execute(
                select(Post)
                .where(Post.user_id == user_id, Post.status == "published")
                .order_by(desc(Post.published_at))
                .limit(50)
            )
        ).scalars().all()

    if not posts:
        return {}

    scored = [(p, _traction(p)) for p in posts]
    scored.sort(key=lambda x: x[1], reverse=True)
    cutoff = max(1, len(scored) // 4)
    winners = [p for p, _ in scored[:cutoff]]

    focus_areas: list[str] = []
    async with AsyncSessionLocal() as db:
        for p in winners:
            if not p.research_id:
                continue
            topic = (
                await db.execute(
                    select(ResearchTopic).where(ResearchTopic.id == p.research_id)
                )
            ).scalar_one_or_none()
            if topic and topic.sources:
                first = topic.sources[0] if isinstance(topic.sources, list) else {}
                stance = first.get("stance", {}) if isinstance(first, dict) else {}
                fa = stance.get("focus_area")
                if fa:
                    focus_areas.append(fa)

    hook_types = Counter()
    for p in winners:
        hook = p.content[:80].lower()
        if "?" in hook[:40]:
            hook_types["question"] += 1
        elif any(w in hook for w in ("wrong", "myth", "overrated", "don't")):
            hook_types["contrarian_claim"] += 1
        elif hook[:20].replace(".", "").isdigit() or "%" in hook[:30]:
            hook_types["data_lead"] += 1
        else:
            hook_types["story_open"] += 1

    total = sum(hook_types.values()) or 1
    affinites = {k: round(v / total, 2) for k, v in hook_types.items()}

    return {
        "winning_focus_areas": list(dict.fromkeys(focus_areas)),
        "winning_hook_types": dict(hook_types),
        "hook_affinites": affinites,
        "winner_count": len(winners),
        "top_engagement": _traction(winners[0]) if winners else 0,
    }


async def apply_feedback(user_id: UUID) -> dict[str, Any]:
    patterns = await compute_winning_patterns(user_id)
    if not patterns:
        return {"status": "skipped", "reason": "no_data"}

    async with AsyncSessionLocal() as db:
        profile = (
            await db.execute(
                select(UserVoiceProfile).where(UserVoiceProfile.user_id == user_id)
            )
        ).scalar_one_or_none()
        if not profile:
            from services.brain.queries import default_focus_areas

            profile = UserVoiceProfile(user_id=user_id, focus_areas=default_focus_areas())
            db.add(profile)
        if patterns.get("hook_affinites"):
            existing = profile.hook_affinites or {}
            profile.hook_affinites = {**existing, **patterns["hook_affinites"]}
        profile.insights = patterns
        await db.commit()

    logger.info("brain_feedback_applied", user_id=str(user_id), patterns=patterns)
    return {"status": "complete", "patterns": patterns}


async def apply_feedback_all() -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        users = (await db.execute(select(User).where(User.is_active.is_(True)))).scalars().all()

    results = []
    for u in users:
        try:
            results.append({**await apply_feedback(u.id), "user_id": str(u.id)})
        except Exception as exc:
            logger.error("feedback_user_failed", user_id=str(u.id), error=str(exc))
            results.append({"user_id": str(u.id), "status": "error", "error": str(exc)})
    return {"users": results}


async def boost_score_for_user(user_id: UUID, focus_area: str, base_score: float) -> float:
    """Subtle relevance boost when focus_area matches user's recent winners."""
    async with AsyncSessionLocal() as db:
        profile = (
            await db.execute(
                select(UserVoiceProfile).where(UserVoiceProfile.user_id == user_id)
            )
        ).scalar_one_or_none()
    if not profile or not profile.insights:
        return base_score
    winners = profile.insights.get("winning_focus_areas", [])
    if focus_area in winners:
        return min(base_score + 0.1, 1.0)
    return base_score
