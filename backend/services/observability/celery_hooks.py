"""Celery signal handlers for structured task logging and metrics."""
from __future__ import annotations

import time
from typing import Any

import structlog
from celery.signals import task_failure, task_postrun, task_prerun, task_retry

from services.observability.context import bind_celery_context, clear_context
from services.observability.metrics import record_celery_task

logger = structlog.get_logger(__name__)

_task_started_at: dict[str, float] = {}


def register_celery_observability() -> None:
    """Connect Celery signals once per worker process."""
    task_prerun.connect(_on_task_prerun, weak=False)
    task_postrun.connect(_on_task_postrun, weak=False)
    task_failure.connect(_on_task_failure, weak=False)
    task_retry.connect(_on_task_retry, weak=False)


def _on_task_prerun(
    task_id: str | None = None,
    task: Any = None,
    args: tuple[Any, ...] | None = None,
    kwargs: dict[str, Any] | None = None,
    **_: Any,
) -> None:
    if not task_id or task is None:
        return

    extra: dict[str, str] = {}
    if kwargs and kwargs.get("user_id"):
        extra["user_id"] = str(kwargs["user_id"])
    elif args:
        extra["user_id"] = str(args[0])

    bind_celery_context(task_id=task_id, task_name=task.name, **extra)
    _task_started_at[task_id] = time.perf_counter()
    logger.info("celery_task_started", celery_task_id=task_id, celery_task_name=task.name)


def _finish_task(task_id: str | None, task: Any | None, *, state: str) -> None:
    if not task_id or task is None:
        return

    started = _task_started_at.pop(task_id, None)
    duration_ms = (time.perf_counter() - started) * 1000 if started is not None else 0.0
    record_celery_task(task_name=task.name, state=state, duration_ms=duration_ms)

    log_fn = logger.info if state == "success" else logger.error
    log_fn(
        "celery_task_finished",
        celery_task_id=task_id,
        celery_task_name=task.name,
        state=state,
        duration_ms=round(duration_ms, 2),
    )
    clear_context()


def _on_task_postrun(
    task_id: str | None = None,
    task: Any = None,
    state: str | None = None,
    **_: Any,
) -> None:
    if state in ("FAILURE", "RETRY"):
        return
    _finish_task(task_id, task, state="success")


def _on_task_failure(
    task_id: str | None = None,
    task: Any = None,
    **_: Any,
) -> None:
    _finish_task(task_id, task, state="failure")


def _on_task_retry(
    task_id: str | None = None,
    task: Any = None,
    **_: Any,
) -> None:
    if not task_id or task is None:
        return

    started = _task_started_at.get(task_id)
    duration_ms = (time.perf_counter() - started) * 1000 if started is not None else 0.0
    record_celery_task(task_name=task.name, state="retry", duration_ms=duration_ms)
    logger.warning(
        "celery_task_retry",
        celery_task_id=task_id,
        celery_task_name=task.name,
        duration_ms=round(duration_ms, 2),
    )
