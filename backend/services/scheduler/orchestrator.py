"""Celery Beat schedule definition and task status helpers."""
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Beat schedule — all times in ET, expressed in UTC for Celery
# Configurable overrides come from user_settings table at task start time.
BEAT_SCHEDULE = {
    "research-sweep-morning": {
        "task": "services.scheduler.tasks.run_research_sweep",
        "schedule": "0 13 * * *",  # 8 AM ET = 13:00 UTC
        "options": {"queue": "default"},
    },
    "research-sweep-evening": {
        "task": "services.scheduler.tasks.run_research_sweep",
        "schedule": "0 23 * * *",  # 6 PM ET = 23:00 UTC
        "options": {"queue": "default"},
    },
    "content-generation": {
        "task": "services.scheduler.tasks.run_content_generation",
        "schedule": "0 2 * * *",  # 9 PM ET = 02:00 UTC next day
        "options": {"queue": "default"},
    },
    "queue-check": {
        "task": "services.scheduler.tasks.check_publish_queue",
        "schedule": "*/5 * * * *",  # every 5 minutes
        "options": {"queue": "default"},
    },
    "engagement-sweep": {
        "task": "services.scheduler.tasks.run_engagement_sweep",
        "schedule": "0 */4 * * *",  # every 4 hours
        "options": {"queue": "default"},
    },
    "metric-collection": {
        "task": "services.scheduler.tasks.collect_metrics",
        "schedule": "0 4 * * *",  # 11 PM ET = 04:00 UTC
        "options": {"queue": "default"},
    },
    "daily-summary": {
        "task": "services.scheduler.tasks.generate_daily_summary",
        "schedule": "30 1 * * *",  # 8:30 PM ET = 01:30 UTC
        "options": {"queue": "default"},
    },
    "morning-email": {
        "task": "services.scheduler.tasks.send_morning_email",
        "schedule": "0 12 * * *",  # 7 AM ET = 12:00 UTC
        "options": {"queue": "default"},
    },
    "evening-email": {
        "task": "services.scheduler.tasks.send_evening_email",
        "schedule": "0 2 * * *",  # 9 PM ET = 02:00 UTC
        "options": {"queue": "default"},
    },
    "weekly-report": {
        "task": "services.scheduler.tasks.generate_weekly_report",
        "schedule": "0 1 * * 1",  # Sunday 8 PM ET = Monday 01:00 UTC
        "options": {"queue": "default"},
    },
}


async def get_task_statuses() -> list[dict[str, Any]]:
    """Return task schedule info for the dashboard."""
    return [
        {
            "name": name,
            "task": cfg["task"].split(".")[-1],
            "schedule": cfg["schedule"],
        }
        for name, cfg in BEAT_SCHEDULE.items()
    ]
