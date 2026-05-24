import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.engagement import EngagementAction
from models.user import User
from services.auth.deps import get_current_user

router = APIRouter()


@router.get("/log")
async def get_engagement_log(
    post_id: uuid.UUID | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    q = (
        select(EngagementAction)
        .where(EngagementAction.user_id == user.id)
        .order_by(EngagementAction.created_at.desc())
    )
    if post_id:
        q = q.where(EngagementAction.post_id == post_id)
    q = q.offset(offset).limit(limit)
    actions = (await db.execute(q)).scalars().all()
    return {"actions": [_action_to_dict(a) for a in actions]}


@router.post("/trigger")
async def trigger_engagement_sweep(_: User = Depends(get_current_user)) -> dict[str, str]:
    from services.scheduler.tasks import run_engagement_sweep
    task = run_engagement_sweep.delay()
    return {"status": "triggered", "task_id": task.id}


def _action_to_dict(a: EngagementAction) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "post_id": str(a.post_id),
        "original_comment": a.original_comment,
        "reply_text": a.reply_text,
        "status": a.status,
        "posted_at": a.posted_at.isoformat() if a.posted_at else None,
        "created_at": a.created_at.isoformat(),
    }
