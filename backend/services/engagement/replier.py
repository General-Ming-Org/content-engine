"""LinkedIn comment monitoring + reply generation, per-user.

Iterates over all active users with LinkedIn creds configured. For each, polls
comments on their recent published posts and replies using their own access token.
"""
import asyncio
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import httpx
import structlog
from sqlalchemy import select

from database import AsyncSessionLocal
from models.content import Post
from models.engagement import EngagementAction
from models.user import User
from services.ai.claude_client import generate
from services.content.prompts import (
    ENGAGEMENT_REPLY_SYSTEM_PROMPT,
    ENGAGEMENT_REPLY_USER_PROMPT,
)
from services.credentials.store import get_linkedin_credential
from services.engagement.safety import should_skip_comment, validate_reply

logger = structlog.get_logger(__name__)


async def _fetch_comments(access_token: str, linkedin_post_id: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"https://api.linkedin.com/v2/socialActions/{linkedin_post_id}/comments",
            headers={
                "Authorization": f"Bearer {access_token}",
                "X-Restli-Protocol-Version": "2.0.0",
            },
        )
        if resp.status_code != 200:
            logger.warning("linkedin_comments_fetch_failed", status=resp.status_code)
            return []
        return resp.json().get("elements", [])


async def _post_reply(
    access_token: str, person_urn: str, linkedin_post_id: str,
    comment_urn: str, reply_text: str,
) -> bool:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"https://api.linkedin.com/v2/socialActions/{linkedin_post_id}/comments",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
            },
            json={
                "actor": person_urn,
                "message": {"text": reply_text},
                "parentComment": comment_urn,
            },
        )
        return resp.status_code in (200, 201)


async def _generate_reply(post_content: str, comment_text: str) -> str:
    return (await generate(
        task="comment_reply",
        system=ENGAGEMENT_REPLY_SYSTEM_PROMPT,
        user=ENGAGEMENT_REPLY_USER_PROMPT.format(
            post_content=post_content[:500],
            comment_text=comment_text,
        ),
        max_tokens=300,
        temperature=0.7,
    )).strip()


async def _already_replied(db, post_id: uuid.UUID, comment_text: str) -> bool:
    result = await db.execute(
        select(EngagementAction).where(
            EngagementAction.post_id == post_id,
            EngagementAction.original_comment == comment_text,
        )
    )
    return result.scalar_one_or_none() is not None


async def _sweep_user(user_id: UUID) -> dict[str, int]:
    cred = await get_linkedin_credential(user_id)
    if not cred or not cred.get("access_token") or not cred.get("person_urn"):
        return {"replied": 0, "skipped": 0, "errors": 0, "reason": "no_linkedin_cred"}

    lookback = datetime.now(timezone.utc) - timedelta(days=7)
    replied = skipped = errors = 0

    async with AsyncSessionLocal() as db:
        posts = (await db.execute(
            select(Post).where(
                Post.user_id == user_id,
                Post.status == "published",
                Post.linkedin_post_id.isnot(None),
                Post.published_at >= lookback,
            )
        )).scalars().all()

    for post in posts:
        try:
            comments = await _fetch_comments(cred["access_token"], post.linkedin_post_id)
            for comment in comments:
                comment_text = comment.get("message", {}).get("text", "")
                comment_urn = comment.get("$URN", "")
                if not comment_text or not comment_urn:
                    continue

                should_skip, reason = should_skip_comment(comment_text)
                if should_skip:
                    skipped += 1
                    continue

                async with AsyncSessionLocal() as db:
                    if await _already_replied(db, post.id, comment_text):
                        skipped += 1
                        continue

                try:
                    reply = await _generate_reply(post.content, comment_text)
                    is_valid, reason = validate_reply(reply)
                    if not is_valid:
                        logger.warning("reply_validation_failed", reason=reason)
                        skipped += 1
                        continue

                    await asyncio.sleep(random.uniform(180, 480))  # 3-8 minutes

                    success = await _post_reply(
                        cred["access_token"], cred["person_urn"],
                        post.linkedin_post_id, comment_urn, reply,
                    )
                    status = "posted" if success else "failed"

                    async with AsyncSessionLocal() as db:
                        db.add(EngagementAction(
                            id=uuid.uuid4(),
                            user_id=user_id,
                            post_id=post.id,
                            original_comment=comment_text,
                            reply_text=reply,
                            status=status,
                            posted_at=datetime.now(timezone.utc) if success else None,
                        ))
                        await db.commit()

                    if success:
                        replied += 1
                    else:
                        errors += 1
                except Exception as exc:
                    logger.error("reply_generation_failed", user_id=str(user_id), error=str(exc))
                    errors += 1
        except Exception as exc:
            logger.error("comment_fetch_failed", post_id=str(post.id), error=str(exc))
            errors += 1

    return {"replied": replied, "skipped": skipped, "errors": errors}


async def sweep() -> dict[str, Any]:
    """Top-level engagement task — iterates active users."""
    async with AsyncSessionLocal() as db:
        users = (await db.execute(select(User).where(User.is_active.is_(True)))).scalars().all()

    per_user = {}
    for u in users:
        per_user[str(u.id)] = await _sweep_user(u.id)
    return {"users": per_user}
