"""LinkedIn post publishing via official API — per-user tokens from OAuth (Authlib).

OAuth authorization lives in ``linkedin_oauth.py``. Circuit breaker is per-user.
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import structlog
from sqlalchemy import select, update

from database import AsyncSessionLocal
from models.content import Post
from models.settings import UserSetting
from services.credentials.store import get_linkedin_credential, save_linkedin_credential
from services.publishing.linkedin_oauth import (
    LINKEDIN_OAUTH_SCOPES,
    create_authorization_url,
    decode_oauth_state,
    exchange_authorization_code,
    fetch_linkedin_userinfo,
    get_linkedin_redirect_uri,
)

# Re-export for routes and credentials API.
__all__ = [
    "LINKEDIN_OAUTH_SCOPES",
    "complete_oauth",
    "decode_oauth_state",
    "get_linkedin_redirect_uri",
    "get_oauth_url",
    "publish_post",
    "get_post_metrics",
]

logger = structlog.get_logger(__name__)

LINKEDIN_API_BASE = "https://api.linkedin.com/v2"


async def get_oauth_url(user_id: uuid.UUID, redirect_uri: str) -> str:
    """Generate LinkedIn OAuth consent URL (Authlib). ``redirect_uri`` arg kept for API compat."""
    url, _ = await create_authorization_url(user_id)
    return url


async def complete_oauth(user_id: uuid.UUID, code: str, redirect_uri: str) -> None:
    """Exchange code, fetch person URN, persist creds. ``redirect_uri`` is implicit in Authlib client."""
    del redirect_uri  # Authlib client uses get_linkedin_redirect_uri()
    tokens = await exchange_authorization_code(user_id, code)
    access = tokens["access_token"]
    refresh = tokens.get("refresh_token", "")
    expires_in = int(tokens.get("expires_in", 0))
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in) if expires_in else None
    userinfo = await fetch_linkedin_userinfo(access)
    person_urn = f"urn:li:person:{userinfo['sub']}"
    await save_linkedin_credential(user_id, access, refresh, person_urn, expires_at)


async def _get_headers_for(user_id: uuid.UUID) -> dict[str, str]:
    cred = await get_linkedin_credential(user_id)
    if not cred or not cred.get("access_token"):
        raise RuntimeError(f"LinkedIn not authorized for user {user_id}")
    return {
        "Authorization": f"Bearer {cred['access_token']}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }


async def _check_circuit_breaker(user_id: uuid.UUID) -> bool:
    """Per-user circuit breaker — one user's 429 doesn't pause everyone."""
    async with AsyncSessionLocal() as db:
        setting = (
            await db.execute(
                select(UserSetting).where(
                    UserSetting.user_id == user_id,
                    UserSetting.key == "circuit_breaker",
                )
            )
        ).scalar_one_or_none()
        if setting and setting.value.get("linkedin_paused_until"):
            paused_until = datetime.fromisoformat(setting.value["linkedin_paused_until"])
            if datetime.now(timezone.utc) < paused_until:
                logger.warning("linkedin_circuit_open", user_id=str(user_id), paused_until=setting.value["linkedin_paused_until"])
                return False
    return True


async def _open_circuit_breaker(user_id: uuid.UUID) -> None:
    paused_until = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    async with AsyncSessionLocal() as db:
        existing = (
            await db.execute(
                select(UserSetting).where(
                    UserSetting.user_id == user_id,
                    UserSetting.key == "circuit_breaker",
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.value = {"linkedin_paused_until": paused_until, "pause_duration_minutes": 60}
        else:
            db.add(UserSetting(
                user_id=user_id,
                key="circuit_breaker",
                value={"linkedin_paused_until": paused_until, "pause_duration_minutes": 60},
            ))
        await db.commit()
    logger.warning("linkedin_circuit_opened", user_id=str(user_id), paused_until=paused_until)


async def publish_post(post_id: str) -> dict[str, Any]:
    """Publish a LinkedIn post. Idempotent. Reads creds from the owning user."""
    try:
        return await _publish_post_impl(post_id)
    except Exception as exc:
        from services.publishing.failures import mark_post_failed

        await mark_post_failed(post_id, str(exc))
        raise


async def _publish_post_impl(post_id: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Post).where(Post.id == uuid.UUID(post_id)))
        post = result.scalar_one_or_none()
        if not post:
            return {"error": f"Post {post_id} not found"}

        if post.linkedin_post_id:
            logger.info("linkedin_post_already_published", post_id=post_id)
            return {"status": "already_published", "linkedin_post_id": post.linkedin_post_id}

        if not await _check_circuit_breaker(post.user_id):
            raise RuntimeError("LinkedIn circuit breaker open — operations paused")

        cred = await get_linkedin_credential(post.user_id)
        if not cred or not cred.get("access_token") or not cred.get("person_urn"):
            raise RuntimeError(f"LinkedIn not authorized for user {post.user_id}")

        payload = {
            "author": cred["person_urn"],
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": post.content},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.post(
                    f"{LINKEDIN_API_BASE}/ugcPosts",
                    headers=await _get_headers_for(post.user_id),
                    json=payload,
                )
                if resp.status_code == 429:
                    await _open_circuit_breaker(post.user_id)
                    raise RuntimeError("LinkedIn rate limit hit — circuit breaker opened")
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.error("linkedin_publish_http_error", status=exc.response.status_code)
                raise

        linkedin_post_id = resp.headers.get("x-restli-id", resp.json().get("id", ""))
        await db.execute(
            update(Post)
            .where(Post.id == post.id)
            .values(
                status="published",
                published_at=datetime.now(timezone.utc),
                linkedin_post_id=linkedin_post_id,
            )
        )
        await db.commit()
        logger.info("linkedin_post_published", post_id=post_id, linkedin_id=linkedin_post_id)

        from services.ai.ingestion import index_published_post

        await index_published_post(
            user_id=post.user_id,
            post_id=post.id,
            content=post.content,
            domain="software_eng",
            voice_style=post.voice_style,
            metadata={"linkedin_post_id": linkedin_post_id},
        )
        return {"status": "published", "linkedin_post_id": linkedin_post_id}


async def get_post_metrics(user_id: uuid.UUID, linkedin_post_id: str) -> dict[str, Any]:
    if not await _check_circuit_breaker(user_id):
        return {}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{LINKEDIN_API_BASE}/socialMetadata/{linkedin_post_id}",
            headers=await _get_headers_for(user_id),
        )
        if resp.status_code != 200:
            logger.warning("linkedin_metrics_failed", status=resp.status_code)
            return {}
        data = resp.json()
        return {
            "likes": data.get("numLikes", 0),
            "comments": data.get("numComments", 0),
            "shares": data.get("numShares", 0),
        }
