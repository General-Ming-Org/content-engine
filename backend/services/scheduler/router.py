"""Scheduler routes — system-wide triggers gated to admins."""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from models.user import User
from services.auth.deps import get_current_user, require_admin

router = APIRouter()

TASK_MAP = {
    "brain_harvest": "run_brain_harvest",
    "brain_personality_refresh": "run_brain_personality_refresh",
    "research_sweep": "run_research_sweep",
    "content_generation": "run_content_generation",
    "queue_check": "check_publish_queue",
    "engagement_sweep": "run_engagement_sweep",
    "metric_collection": "collect_metrics",
    "daily_summary": "generate_daily_summary",
    "weekly_report": "generate_weekly_report",
    "morning_email": "send_morning_email",
    "evening_email": "send_evening_email",
    "reembed_corpus": "reembed_corpus",
}


@router.get("/status")
async def scheduler_status(_: User = Depends(get_current_user)) -> dict[str, Any]:
    from services.scheduler.orchestrator import get_task_statuses
    return {"tasks": await get_task_statuses()}


@router.post("/trigger/{task_name}")
async def trigger_task(
    task_name: str,
    user: User = Depends(require_admin),
) -> dict[str, str]:
    """Admin-only — these tasks run globally and fan out to all users."""
    from services.common.rate_limit import enforce_rate_limit

    if task_name not in TASK_MAP:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown task '{task_name}'. Valid: {list(TASK_MAP.keys())}",
        )

    if task_name in ("morning_email", "evening_email"):
        await enforce_rate_limit(
            f"scheduler:email:{task_name}:{user.id}",
            300,
            message="Test/digest emails are limited to once every 5 minutes.",
        )
    else:
        await enforce_rate_limit(
            f"scheduler:trigger:{task_name}:{user.id}",
            30,
            message="Please wait before triggering this task again.",
        )
    import services.scheduler.tasks as task_module
    fn = getattr(task_module, TASK_MAP[task_name], None)
    if fn is None:
        raise HTTPException(status_code=500, detail="Task function not found")
    result = fn.delay()
    return {"status": "triggered", "task_name": task_name, "task_id": result.id}
