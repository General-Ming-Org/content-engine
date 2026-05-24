import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.notifications import Notification
from models.user import User
from services.auth.deps import get_current_user

router = APIRouter()


@router.get("")
async def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(50, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    q = (
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
    )
    if unread_only:
        q = q.where(Notification.is_read.is_(False))
    q = q.limit(limit)
    notifications = (await db.execute(q)).scalars().all()
    return {"notifications": [_notif_to_dict(n) for n in notifications]}


@router.patch("/{notification_id}/read")
async def mark_read(
    notification_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    await db.execute(
        update(Notification)
        .where(Notification.id == notification_id, Notification.user_id == user.id)
        .values(is_read=True)
    )
    return {"status": "ok"}


@router.patch("/read-all")
async def mark_all_read(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user.id)
        .values(is_read=True)
    )
    return {"status": "ok"}


@router.get("/unread-count")
async def unread_count(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    q = (
        select(func.count()).select_from(Notification)
        .where(Notification.user_id == user.id, Notification.is_read.is_(False))
    )
    count = (await db.execute(q)).scalar_one()
    return {"count": count}


def _notif_to_dict(n: Notification) -> dict[str, Any]:
    return {
        "id": str(n.id),
        "type": n.type,
        "title": n.title,
        "message": n.message,
        "is_read": n.is_read,
        "emailed": n.emailed,
        "created_at": n.created_at.isoformat(),
    }
