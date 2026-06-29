"""Per-user tone preferences — loaded from user_settings and injected into generation."""
from typing import Any
from uuid import UUID

from sqlalchemy import select

from database import AsyncSessionLocal
from models.settings import UserSetting

DEFAULT_TONE: dict[str, Any] = {
    "voice_rotation": ["opinionated", "analytical", "tutorial"],
    "emoji_max": 2,
    "hashtag_min": 3,
    "hashtag_max": 5,
}


async def load_tone_preferences(user_id: UUID) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(UserSetting).where(
                    UserSetting.user_id == user_id,
                    UserSetting.key == "tone_preferences",
                )
            )
        ).scalar_one_or_none()
    if row and isinstance(row.value, dict):
        return {**DEFAULT_TONE, **row.value}
    return dict(DEFAULT_TONE)


def tone_system_constraints(tone: dict[str, Any]) -> str:
    emoji_max = int(tone.get("emoji_max", DEFAULT_TONE["emoji_max"]))
    hashtag_min = int(tone.get("hashtag_min", DEFAULT_TONE["hashtag_min"]))
    hashtag_max = int(tone.get("hashtag_max", DEFAULT_TONE["hashtag_max"]))
    return (
        f"- 0-{emoji_max} emojis maximum. If you use one, it must add meaning, not decoration.\n"
        f"- {hashtag_min}-{hashtag_max} hashtags at the end, on their own line, researched and relevant"
    )


def validate_hashtags(content: str, tone: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    hashtag_min = int(tone.get("hashtag_min", DEFAULT_TONE["hashtag_min"]))
    hashtag_max = int(tone.get("hashtag_max", DEFAULT_TONE["hashtag_max"]))
    hashtag_count = content.count("#")
    if hashtag_count < hashtag_min:
        issues.append(f"Too few hashtags: {hashtag_count} (min {hashtag_min})")
    if hashtag_count > hashtag_max:
        issues.append(f"Too many hashtags: {hashtag_count} (max {hashtag_max})")
    return issues


def pick_voice_style(tone: dict[str, Any], default: str = "opinionated") -> str:
    rotation = tone.get("voice_rotation") or DEFAULT_TONE["voice_rotation"]
    if not rotation:
        return default
    import hashlib

    idx = int(hashlib.md5(str(rotation).encode()).hexdigest(), 16) % len(rotation)
    return rotation[idx] if isinstance(rotation, list) else default
