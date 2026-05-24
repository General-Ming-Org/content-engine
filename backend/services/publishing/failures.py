"""Publish failure handling — terminal states, user notifications, no retry spam."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

import structlog
from sqlalchemy import or_, select, update

from database import AsyncSessionLocal
from models.content import Article, Post
from models.notifications import Notification

logger = structlog.get_logger(__name__)

Platform = Literal["linkedin", "substack"]

# One failure alert (in-app + email) per content item for this long.
PUBLISH_FAIL_NOTIFY_TTL_SECONDS = 30 * 24 * 3600

PERMANENT_ERROR_MARKERS = (
    "not authorized",
    "not configured",
    "credentials",
    "circuit breaker",
    "publication_url missing",
    "login failed",
)


def is_permanent_publish_error(message: str) -> bool:
    lower = message.lower()
    return any(marker in lower for marker in PERMANENT_ERROR_MARKERS)


def publish_failure_title(platform: Platform, item_id: str | UUID) -> str:
    """Stable notification title — one row per post/article for deduplication."""
    label = "LinkedIn post" if platform == "linkedin" else "Substack article"
    return f"{label} publish failed · {item_id}"


def _notify_slot_key(platform: Platform, item_id: str | UUID) -> str:
    return f"publish-fail-notify:{platform}:{item_id}"


async def mark_post_failed(post_id: str | UUID, error: str) -> UUID | None:
    """Move a post out of the auto-publish queue. Returns owner user_id if updated."""
    pid = post_id if isinstance(post_id, UUID) else uuid.UUID(str(post_id))
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(select(Post).where(Post.id == pid))
        ).scalar_one_or_none()
        if not row:
            return None
        if row.status in ("published", "cancelled"):
            return row.user_id
        if row.status != "failed":
            await db.execute(
                update(Post)
                .where(Post.id == pid)
                .values(status="failed", queued_at=None)
            )
            await db.commit()
            logger.info("post_marked_failed", post_id=str(pid), error=error[:200])
        return row.user_id


async def mark_article_failed(article_id: str | UUID, error: str) -> UUID | None:
    aid = article_id if isinstance(article_id, UUID) else uuid.UUID(str(article_id))
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(select(Article).where(Article.id == aid))
        ).scalar_one_or_none()
        if not row:
            return None
        if row.status in ("published", "cancelled"):
            return row.user_id
        if row.status != "failed":
            await db.execute(
                update(Article)
                .where(Article.id == aid)
                .values(status="failed", queued_at=None)
            )
            await db.commit()
            logger.info("article_marked_failed", article_id=str(aid), error=error[:200])
        return row.user_id


async def _already_notified_in_db(
    user_id: UUID,
    title: str,
    item_id: str | UUID,
) -> bool:
    """DB fallback — prior error for this item (stable title or legacy message body)."""
    item_s = str(item_id)
    async with AsyncSessionLocal() as db:
        existing = (
            await db.execute(
                select(Notification.id).where(
                    Notification.user_id == user_id,
                    Notification.type == "error",
                    or_(
                        Notification.title == title,
                        Notification.message.contains(item_s),
                    ),
                ).limit(1)
            )
        ).scalar_one_or_none()
    return existing is not None


async def _claim_publish_failure_notify(
    platform: Platform,
    item_id: str | UUID,
    user_id: UUID,
) -> bool:
    """True if this process may send the one allowed failure alert for this item."""
    from services.common.rate_limit import acquire_once

    title = publish_failure_title(platform, item_id)
    slot = _notify_slot_key(platform, item_id)
    result = await acquire_once(slot, PUBLISH_FAIL_NOTIFY_TTL_SECONDS)
    if result == "acquired":
        return True
    if result == "duplicate":
        logger.info("publish_failure_notify_slot_taken", platform=platform, item_id=str(item_id))
        return False
    # Redis down — allow only if we have never recorded this title for the user.
    logger.warning("publish_failure_notify_redis_unavailable", item_id=str(item_id))
    return not await _already_notified_in_db(user_id, title, item_id)


async def notify_publish_failure(
    user_id: UUID,
    *,
    platform: Platform,
    item_id: str | UUID,
    error: str,
    email: bool = True,
) -> None:
    """In-app + email at most once per post/article (atomic Redis claim + DB title)."""
    title = publish_failure_title(platform, item_id)
    short_err = error.strip()[:500]
    message = (
        f"Your content could not be published and was removed from the 1-hour queue. "
        f"Fix the issue in Settings, then retry from the Calendar.\n\n"
        f"Reason: {short_err}"
    )

    if not await _claim_publish_failure_notify(platform, item_id, user_id):
        return

    if await _already_notified_in_db(user_id, title, item_id):
        logger.info(
            "publish_failure_notification_deduped_db",
            user_id=str(user_id),
            item_id=str(item_id),
        )
        return

    from services.notifications.notifier import create_user_error

    await create_user_error(user_id, title, message, send_email=email)


async def handle_publish_exception(
    *,
    platform: Platform,
    item_id: str | UUID,
    error: Exception | str,
    notify: bool = True,
) -> UUID | None:
    """Mark failed + optional user notification. Used by queue processor and Celery tasks."""
    err = str(error)
    if platform == "linkedin":
        user_id = await mark_post_failed(item_id, err)
    else:
        user_id = await mark_article_failed(item_id, err)
    if notify and user_id:
        await notify_publish_failure(
            user_id,
            platform=platform,
            item_id=item_id,
            error=err,
        )
    return user_id
