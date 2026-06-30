"""Structlog contextvar helpers for request / user / task correlation."""
from __future__ import annotations

import uuid

import structlog


def new_request_id() -> str:
    return str(uuid.uuid4())


def bind_request_context(*, request_id: str, method: str, path: str) -> None:
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        http_method=method,
        http_path=path,
    )


def bind_user_context(*, user_id: str) -> None:
    structlog.contextvars.bind_contextvars(user_id=user_id)


def bind_celery_context(*, task_id: str, task_name: str, **extra: str) -> None:
    structlog.contextvars.bind_contextvars(
        celery_task_id=task_id,
        celery_task_name=task_name,
        **extra,
    )


def clear_context() -> None:
    structlog.contextvars.clear_contextvars()
