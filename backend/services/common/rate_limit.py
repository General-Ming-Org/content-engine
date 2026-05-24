"""Redis-backed rate limiting for user-triggered side effects (email, OAuth, etc.)."""
from __future__ import annotations

from typing import Literal

import structlog
from fastapi import HTTPException, status

from config import get_settings

logger = structlog.get_logger(__name__)

AcquireResult = Literal["acquired", "duplicate", "unavailable"]

_redis = None


async def _redis_client():
    global _redis
    if _redis is None:
        import redis.asyncio as aioredis

        _redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis


async def acquire_once(key: str, ttl_seconds: int) -> AcquireResult:
    """Atomically claim a one-time slot (e.g. one failure email per post)."""
    try:
        client = await _redis_client()
        acquired = await client.set(f"rl:{key}", "1", nx=True, ex=ttl_seconds)
        return "acquired" if acquired else "duplicate"
    except Exception as exc:
        logger.error("rate_limit_redis_unavailable", key=key, error=str(exc))
        return "unavailable"


async def acquire_rate_limit(key: str, window_seconds: int) -> bool:
    """Return True if this is the first action in the window, False if rate limited."""
    result = await acquire_once(key, window_seconds)
    if result == "acquired":
        return True
    if result == "duplicate":
        return False
    # Fail closed when Redis is down.
    return False


async def enforce_rate_limit(
    key: str,
    window_seconds: int,
    *,
    message: str = "Too many requests. Please wait before trying again.",
) -> None:
    """Raise HTTP 429 with Retry-After when the limit is exceeded."""
    if await acquire_rate_limit(key, window_seconds):
        return
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=message,
        headers={"Retry-After": str(window_seconds)},
    )
