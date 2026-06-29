#!/usr/bin/env python3
"""CLI for manually triggering any pipeline task without the dashboard."""
import argparse
import asyncio
import sys

sys.path.insert(0, "backend")


TASKS = {
    "research": "Run research sweep across all domains",
    "generate": "Generate content from top unassigned topics",
    "queue": "Process 1-hour auto-publish queue",
    "engage": "Run engagement sweep (reply to comments)",
    "metrics": "Collect metrics from all platforms",
    "daily-report": "Generate daily summary report",
    "weekly-report": "Generate weekly deep-dive report",
    "morning-email": "Send morning preview digest",
    "evening-email": "Send evening recap digest",
}


async def run_task(task: str, dry_run: bool = False, user_id: str | None = None):
    if task == "research":
        import uuid

        from sqlalchemy import select

        from database import AsyncSessionLocal
        from models.user import User
        from services.research.searcher import sweep

        uid: uuid.UUID
        if user_id:
            uid = uuid.UUID(user_id)
        else:
            async with AsyncSessionLocal() as db:
                row = (
                    await db.execute(
                        select(User.id).where(User.is_active.is_(True)).order_by(User.created_at).limit(1)
                    )
                ).scalar_one_or_none()
                if row is None:
                    raise RuntimeError("No active user found — pass --user-id")
                uid = row
        result = await sweep(uid)
    elif task == "generate":
        from services.content.calendar import generate_scheduled_content
        result = await generate_scheduled_content()
    elif task == "queue":
        from services.publishing.queue_manager import process_queue
        result = await process_queue()
    elif task == "engage":
        from services.engagement.replier import sweep
        result = await sweep()
    elif task == "metrics":
        from services.analytics.collectors import collect_all_metrics
        result = await collect_all_metrics()
    elif task == "daily-report":
        from services.analytics.report_generator import generate_daily
        result = await generate_daily()
    elif task == "weekly-report":
        from services.analytics.report_generator import generate_weekly
        result = await generate_weekly()
    elif task == "morning-email":
        from services.notifications.email_digest import send_morning_digest
        result = await send_morning_digest()
    elif task == "evening-email":
        from services.notifications.email_digest import send_evening_digest
        result = await send_evening_digest()
    else:
        print(f"Unknown task: {task}")
        sys.exit(1)

    print(f"Result: {result}")


def main():
    parser = argparse.ArgumentParser(description="Content Engine Manual Trigger")
    parser.add_argument("task", choices=list(TASKS.keys()), help="Task to run")
    parser.add_argument("--dry-run", action="store_true", help="Preview without executing")
    parser.add_argument("--user-id", help="User UUID (required for research when no users exist in DB)")
    args = parser.parse_args()

    if args.dry_run:
        print(f"[DRY RUN] Would run: {args.task} — {TASKS[args.task]}")
        return

    print(f"Running: {args.task} — {TASKS[args.task]}")
    asyncio.run(run_task(args.task, dry_run=args.dry_run, user_id=args.user_id))


if __name__ == "__main__":
    main()
