"""All Celery tasks — thin wrappers that delegate to service modules."""
import asyncio
from typing import Any

import structlog
from celery import Celery
from celery.utils.log import get_task_logger

from config import get_settings
from log_config import configure_logging
from services.scheduler.orchestrator import BEAT_SCHEDULE

settings = get_settings()
# Worker / beat are separate processes; they don't run main.py, so they need
# their own logging bootstrap.
configure_logging(level=settings.log_level, is_production=settings.is_production)
from services.ai.api_keys import sync_provider_env_keys

sync_provider_env_keys()
logger = get_task_logger(__name__)
log = structlog.get_logger(__name__)

def _parse_cron(expr: str):
    from celery.schedules import crontab
    parts = expr.split()
    if len(parts) == 5:
        minute, hour, day_of_month, month_of_year, day_of_week = parts
        return crontab(
            minute=minute,
            hour=hour,
            day_of_month=day_of_month,
            month_of_year=month_of_year,
            day_of_week=day_of_week,
        )
    raise ValueError(f"Invalid cron expression: {expr}")


celery_app = Celery(
    "content_engine",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["services.scheduler.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        name: {
            "task": cfg["task"],
            "schedule": _parse_cron(cfg["schedule"]),
        }
        for name, cfg in BEAT_SCHEDULE.items()
    },
    beat_scheduler="redbeat.RedBeatScheduler",
)


def _run(coro):
    """Run a coroutine from a sync Celery task."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ── Research Brain ────────────────────────────────────────────────────────────

@celery_app.task(name="services.scheduler.tasks.run_brain_harvest", bind=True, max_retries=3)
def run_brain_harvest(self) -> dict[str, Any]:
    try:
        from services.brain.signal_harvester import harvest_signals

        return _run(harvest_signals())
    except Exception as exc:
        log.error("brain_harvest_failed", error=str(exc))
        if self.request.retries >= self.max_retries:
            _notify_error("Brain signal harvest failed", str(exc))
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(name="services.scheduler.tasks.run_brain_personality_refresh", bind=True, max_retries=3)
def run_brain_personality_refresh(self) -> dict[str, Any]:
    try:
        from services.brain.feedback import apply_feedback_all
        from services.brain.personality import refresh_all_profiles

        feedback = _run(apply_feedback_all())
        profiles = _run(refresh_all_profiles())
        return {"feedback": feedback, "profiles": profiles}
    except Exception as exc:
        log.error("brain_personality_refresh_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=120 * (2 ** self.request.retries))


# ── Research ──────────────────────────────────────────────────────────────────

@celery_app.task(name="services.scheduler.tasks.run_research_sweep", bind=True, max_retries=3)
def run_research_sweep(self) -> dict[str, Any]:
    task_id = self.request.id or ""
    from services.research.notify import notify_sweep_outcome
    from services.research.progress import progress_fail, progress_finish, progress_start

    if task_id:
        progress_start(task_id)
    try:
        from services.research.searcher import sweep as research_sweep

        result = _run(research_sweep(task_id or None))
        if task_id:
            progress_finish(task_id, result)
        _run(notify_sweep_outcome(result))
        return result
    except Exception as exc:
        log.error("research_sweep_failed", error=str(exc))
        if task_id:
            progress_fail(task_id, str(exc))
        if self.request.retries >= self.max_retries:
            _notify_error("Research sweep failed", str(exc))
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


# ── Content ───────────────────────────────────────────────────────────────────

@celery_app.task(name="services.scheduler.tasks.run_content_generation", bind=True, max_retries=3)
def run_content_generation(self) -> dict[str, Any]:
    try:
        from services.content.calendar import generate_scheduled_content
        return _run(generate_scheduled_content())
    except Exception as exc:
        log.error("content_generation_failed", error=str(exc))
        _notify_error("Content generation failed", str(exc))
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(name="services.scheduler.tasks.generate_content_for_topic", bind=True, max_retries=3)
def generate_content_for_topic(self, research_topic_id: str, user_id: str) -> dict[str, Any]:
    from uuid import UUID

    task_id = self.request.id or ""
    try:
        from services.content.calendar import generate_for_topic
        return _run(generate_for_topic(research_topic_id, UUID(user_id), task_id or None))
    except Exception as exc:
        log.error("content_for_topic_failed", topic_id=research_topic_id, user_id=user_id, error=str(exc))
        if task_id:
            from services.content.progress import progress_fail

            progress_fail(task_id, str(exc))
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


# ── Publishing ────────────────────────────────────────────────────────────────

@celery_app.task(name="services.scheduler.tasks.check_publish_queue", bind=True, max_retries=1)
def check_publish_queue(self) -> dict[str, Any]:
    """Process due queue items. Per-item failures are handled inside process_queue."""
    from services.publishing.queue_manager import process_queue

    return _run(process_queue())


def _handle_celery_publish_failure(
    self,
    *,
    platform: str,
    item_id: str,
    exc: Exception,
) -> dict[str, Any]:
    from services.publishing.failures import handle_publish_exception, is_permanent_publish_error

    err = str(exc)
    log.error(f"{platform}_publish_failed", item_id=item_id, error=err)
    _run(
        handle_publish_exception(
            platform="linkedin" if platform == "linkedin" else "substack",
            item_id=item_id,
            error=exc,
            notify=self.request.retries >= self.max_retries or is_permanent_publish_error(err),
        )
    )
    if is_permanent_publish_error(err):
        return {"status": "failed", "error": err, "retries": self.request.retries}
    if self.request.retries >= self.max_retries:
        return {"status": "failed", "error": err, "retries": self.request.retries}
    countdown = 60 * (2 ** self.request.retries) if platform == "linkedin" else 120 * (2 ** self.request.retries)
    raise self.retry(exc=exc, countdown=countdown)


@celery_app.task(name="services.scheduler.tasks.publish_linkedin_post", bind=True, max_retries=2)
def publish_linkedin_post(self, post_id: str) -> dict[str, Any]:
    try:
        from services.publishing.linkedin_api import publish_post
        return _run(publish_post(post_id))
    except Exception as exc:
        return _handle_celery_publish_failure(self, platform="linkedin", item_id=post_id, exc=exc)


@celery_app.task(name="services.scheduler.tasks.publish_substack_article", bind=True, max_retries=2)
def publish_substack_article(self, article_id: str) -> dict[str, Any]:
    try:
        from services.publishing.substack_auto import publish_article
        return _run(publish_article(article_id))
    except Exception as exc:
        return _handle_celery_publish_failure(self, platform="substack", item_id=article_id, exc=exc)


# ── Engagement ────────────────────────────────────────────────────────────────

@celery_app.task(name="services.scheduler.tasks.run_engagement_sweep", bind=True, max_retries=3)
def run_engagement_sweep(self) -> dict[str, Any]:
    try:
        from services.engagement.replier import sweep as engagement_sweep
        return _run(engagement_sweep())
    except Exception as exc:
        log.error("engagement_sweep_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


# ── Analytics ─────────────────────────────────────────────────────────────────

@celery_app.task(name="services.scheduler.tasks.collect_metrics", bind=True, max_retries=3)
def collect_metrics(self) -> dict[str, Any]:
    try:
        from services.analytics.collectors import collect_all_metrics
        return _run(collect_all_metrics())
    except Exception as exc:
        log.error("metric_collection_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(name="services.scheduler.tasks.generate_daily_summary", bind=True, max_retries=3)
def generate_daily_summary(self) -> dict[str, Any]:
    try:
        from services.analytics.report_generator import generate_daily
        return _run(generate_daily())
    except Exception as exc:
        log.error("daily_summary_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(name="services.scheduler.tasks.generate_weekly_report", bind=True, max_retries=3)
def generate_weekly_report(self) -> dict[str, Any]:
    try:
        from services.analytics.report_generator import generate_weekly
        return _run(generate_weekly())
    except Exception as exc:
        log.error("weekly_report_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=120 * (2 ** self.request.retries))


# ── AI / Vector store maintenance ─────────────────────────────────────────────

@celery_app.task(name="services.scheduler.tasks.reembed_corpus", bind=True, max_retries=2)
def reembed_corpus(self) -> dict[str, Any]:
    """Re-embed all stored content into the active embedding model's collection.
    Triggered when the embedding model changes; safe to run repeatedly."""
    try:
        from services.ai.reembed import reembed_corpus as run
        return _run(run())
    except Exception as exc:
        log.error("reembed_corpus_failed", error=str(exc))
        _notify_error("Re-embed corpus failed", str(exc))
        raise self.retry(exc=exc, countdown=300 * (2 ** self.request.retries))


# ── Notifications ─────────────────────────────────────────────────────────────

@celery_app.task(name="services.scheduler.tasks.send_morning_email", bind=True, max_retries=3)
def send_morning_email(self) -> dict[str, Any]:
    try:
        from services.notifications.email_digest import send_morning_digest
        return _run(send_morning_digest())
    except Exception as exc:
        log.error("morning_email_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(name="services.scheduler.tasks.send_evening_email", bind=True, max_retries=3)
def send_evening_email(self) -> dict[str, Any]:
    try:
        from services.notifications.email_digest import send_evening_digest
        return _run(send_evening_digest())
    except Exception as exc:
        log.error("evening_email_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _notify_error(title: str, message: str) -> None:
    """Fire-and-forget: create a dashboard error notification."""
    try:
        from services.notifications.notifier import create_error_notification
        _run(create_error_notification(title, message))
    except Exception:
        pass
