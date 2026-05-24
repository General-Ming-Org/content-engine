"""Research routes — shared pool, authenticated reads.

Research topics are intentionally shared across users (lowest-cost mode). Any
authenticated user can list them and filter by their own domain prefs.
Pin/archive (status changes) require admin role since they affect the shared pool.
"""
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.research import ResearchTopic
from models.user import User
from services.auth.deps import get_current_user, require_admin

router = APIRouter()


@router.get("/topics")
async def list_topics(
    domain: str | None = Query(None),
    status: str | None = Query(None),
    min_score: float | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    q = select(ResearchTopic).order_by(ResearchTopic.relevance_score.desc().nullslast())
    if domain:
        q = q.where(ResearchTopic.domain == domain)
    if status:
        q = q.where(ResearchTopic.status == status)
    if min_score is not None:
        q = q.where(ResearchTopic.relevance_score >= min_score)
    q = q.offset(offset).limit(limit)
    topics = (await db.execute(q)).scalars().all()
    return {"topics": [_topic_to_dict(t) for t in topics], "total": len(topics)}


@router.post("/trigger")
async def trigger_research(_: User = Depends(require_admin)) -> dict[str, str]:
    """Admin-only — the research sweep is global and writes to the shared pool."""
    from services.scheduler.tasks import run_research_sweep
    task = run_research_sweep.delay()
    return {"status": "triggered", "task_id": task.id}


@router.get("/sweep/status")
async def research_sweep_status(
    task_id: str | None = Query(None),
    _: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Poll running or recently finished research sweep progress."""
    from services.research.progress import get_progress

    progress = await get_progress(task_id)
    if progress is None:
        return {"active": False, "progress": None}
    return {"active": progress.get("status") == "running", "progress": progress}


@router.patch("/topics/{topic_id}")
async def update_topic(
    topic_id: uuid.UUID,
    payload: dict[str, Any],
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Admin-only — pinning/archiving changes the pool state for all users."""
    allowed_fields = {"status"}
    update_data = {k: v for k, v in payload.items() if k in allowed_fields}
    if not update_data:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    await db.execute(
        update(ResearchTopic).where(ResearchTopic.id == topic_id).values(**update_data)
    )
    topic = (
        await db.execute(select(ResearchTopic).where(ResearchTopic.id == topic_id))
    ).scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    return _topic_to_dict(topic)


def _topic_to_dict(t: ResearchTopic) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "title": t.title,
        "summary": t.summary,
        "sources": t.sources,
        "domain": t.domain,
        "relevance_score": t.relevance_score,
        "status": t.status,
        "created_at": t.created_at.isoformat(),
    }
