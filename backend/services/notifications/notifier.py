"""Per-user notification helpers.

For scoped errors (e.g. "user X's publish failed"), call create_user_error.
For system-wide errors (Redis down, embedding model unreachable), call
broadcast_admin_error — it fans out to all admin accounts.
"""
import uuid
from datetime import datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy import select, update

from database import AsyncSessionLocal
from models.notifications import Notification
from models.user import User

logger = structlog.get_logger(__name__)


async def create_user_error(
    user_id: UUID,
    title: str,
    message: str,
    *,
    send_email: bool = True,
) -> None:
    """Create an error notification scoped to one user; email optional."""
    async with AsyncSessionLocal() as db:
        notif = Notification(
            id=uuid.uuid4(),
            user_id=user_id,
            type="error",
            title=title,
            message=message,
            is_read=False,
            emailed=False,
            created_at=datetime.now(timezone.utc),
        )
        db.add(notif)
        await db.commit()
    logger.error("user_notification_created", user_id=str(user_id), title=title)

    if not send_email:
        return

    try:
        from services.notifications.alerts import send_alert_email
        await send_alert_email(user_id, title, message)
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(Notification).where(Notification.id == notif.id).values(emailed=True)
            )
            await db.commit()
    except Exception as exc:
        logger.warning("alert_email_failed", user_id=str(user_id), error=str(exc))


async def create_user_system(user_id: UUID, title: str, message: str) -> None:
    async with AsyncSessionLocal() as db:
        db.add(Notification(
            id=uuid.uuid4(),
            user_id=user_id,
            type="system",
            title=title,
            message=message,
            is_read=False,
            emailed=False,
            created_at=datetime.now(timezone.utc),
        ))
        await db.commit()


async def broadcast_admin_error(title: str, message: str) -> None:
    """For system-wide problems with no specific user attribution. Notifies all admins."""
    async with AsyncSessionLocal() as db:
        admins = (
            await db.execute(select(User).where(User.role == "admin", User.is_active.is_(True)))
        ).scalars().all()
    for admin in admins:
        await create_user_error(admin.id, title, message)


# Back-compat shims — old callers passed no user_id.
async def create_error_notification(title: str, message: str) -> None:
    """Deprecated: prefer create_user_error(user_id, ...) or broadcast_admin_error."""
    await broadcast_admin_error(title, message)


async def create_system_notification(title: str, message: str) -> None:
    """Deprecated: prefer create_user_system(user_id, ...)."""
    async with AsyncSessionLocal() as db:
        admins = (
            await db.execute(select(User).where(User.role == "admin", User.is_active.is_(True)))
        ).scalars().all()
    for admin in admins:
        await create_user_system(admin.id, title, message)
