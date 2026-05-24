"""Analytics routes — all per-user scoped."""
import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.analytics import Goal, MetricSnapshot, StrategyReport
from models.user import User
from services.auth.deps import get_current_user

router = APIRouter()


@router.get("/metrics")
async def get_metrics(
    platform: str | None = Query(None),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    q = (
        select(MetricSnapshot)
        .where(MetricSnapshot.user_id == user.id)
        .order_by(MetricSnapshot.snapshot_date.desc())
    )
    if platform:
        q = q.where(MetricSnapshot.platform == platform)
    if start_date:
        q = q.where(MetricSnapshot.snapshot_date >= start_date)
    if end_date:
        q = q.where(MetricSnapshot.snapshot_date <= end_date)
    snapshots = (await db.execute(q)).scalars().all()
    return {"snapshots": [_snapshot_to_dict(s) for s in snapshots]}


@router.get("/metrics/current")
async def get_current_metrics(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    latest: dict[str, Any] = {}
    for platform in ("linkedin", "substack"):
        q = (
            select(MetricSnapshot)
            .where(MetricSnapshot.user_id == user.id, MetricSnapshot.platform == platform)
            .order_by(MetricSnapshot.snapshot_date.desc())
            .limit(1)
        )
        result = (await db.execute(q)).scalar_one_or_none()
        latest[platform] = _snapshot_to_dict(result) if result else None
    return latest


@router.get("/benchmarks")
async def get_benchmarks(_: User = Depends(get_current_user)) -> dict[str, Any]:
    from services.analytics.benchmarks import LINKEDIN_BENCHMARKS
    return LINKEDIN_BENCHMARKS


@router.get("/reports")
async def list_reports(
    report_type: str | None = Query(None),
    limit: int = Query(20, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    q = (
        select(StrategyReport)
        .where(StrategyReport.user_id == user.id)
        .order_by(StrategyReport.created_at.desc())
    )
    if report_type:
        q = q.where(StrategyReport.report_type == report_type)
    q = q.limit(limit)
    reports = (await db.execute(q)).scalars().all()
    return {"reports": [_report_to_dict(r) for r in reports]}


@router.get("/reports/latest")
async def get_latest_report(
    report_type: str = Query("weekly_deep_dive"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    q = (
        select(StrategyReport)
        .where(StrategyReport.user_id == user.id, StrategyReport.report_type == report_type)
        .order_by(StrategyReport.created_at.desc())
        .limit(1)
    )
    report = (await db.execute(q)).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="No reports found")
    return _report_to_dict(report)


@router.post("/trigger-collection")
async def trigger_metric_collection(_: User = Depends(get_current_user)) -> dict[str, str]:
    from services.scheduler.tasks import collect_metrics
    task = collect_metrics.delay()
    return {"status": "triggered", "task_id": task.id}


@router.get("/goals")
async def list_goals(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    goals = (await db.execute(
        select(Goal).where(Goal.user_id == user.id).order_by(Goal.created_at.desc())
    )).scalars().all()
    return {"goals": [_goal_to_dict(g) for g in goals]}


@router.post("/goals")
async def create_goal(
    payload: dict[str, Any],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    goal = Goal(
        user_id=user.id,
        metric_name=payload["metric_name"],
        target_value=float(payload["target_value"]),
        target_date=payload["target_date"],
    )
    db.add(goal)
    await db.flush()
    return _goal_to_dict(goal)


@router.put("/goals/{goal_id}")
async def update_goal(
    goal_id: uuid.UUID,
    payload: dict[str, Any],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    q = select(Goal).where(Goal.id == goal_id, Goal.user_id == user.id)
    goal = (await db.execute(q)).scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    for field in ("metric_name", "target_value", "target_date", "status"):
        if field in payload:
            setattr(goal, field, payload[field])
    return _goal_to_dict(goal)


@router.delete("/goals/{goal_id}")
async def delete_goal(
    goal_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    await db.execute(delete(Goal).where(Goal.id == goal_id, Goal.user_id == user.id))
    return {"status": "deleted"}


def _snapshot_to_dict(s: MetricSnapshot) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "snapshot_date": s.snapshot_date.isoformat(),
        "platform": s.platform,
        "data": s.data,
        "created_at": s.created_at.isoformat(),
    }


def _report_to_dict(r: StrategyReport) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "report_type": r.report_type,
        "period_start": r.period_start.isoformat(),
        "period_end": r.period_end.isoformat(),
        "report_json": r.report_json,
        "top_posts": r.top_posts,
        "benchmark_comparison": r.benchmark_comparison,
        "goal_progress": r.goal_progress,
        "created_at": r.created_at.isoformat(),
    }


def _goal_to_dict(g: Goal) -> dict[str, Any]:
    return {
        "id": str(g.id),
        "metric_name": g.metric_name,
        "target_value": g.target_value,
        "target_date": g.target_date.isoformat(),
        "current_value": g.current_value,
        "status": g.status,
        "progress_pct": round((g.current_value / g.target_value * 100), 1) if g.target_value else 0,
        "created_at": g.created_at.isoformat(),
    }
