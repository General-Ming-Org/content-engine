"""In-process metrics counters for HTTP, Celery, and LLM activity."""
from __future__ import annotations

import re
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}"
)

_PROCESS_STARTED_AT = datetime.now(UTC)
_SLOW_REQUEST_MS = 1000.0


def normalize_path(path: str) -> str:
    """Collapse UUID path segments so route metrics stay bounded."""
    return _UUID_RE.sub("{id}", path)


@dataclass
class _RouteStats:
    count: int = 0
    total_duration_ms: float = 0.0
    error_count: int = 0

    @property
    def avg_duration_ms(self) -> float:
        if self.count == 0:
            return 0.0
        return self.total_duration_ms / self.count


@dataclass
class _TaskStats:
    success: int = 0
    failure: int = 0
    retry: int = 0
    total_duration_ms: float = 0.0

    @property
    def total(self) -> int:
        return self.success + self.failure + self.retry

    @property
    def avg_duration_ms(self) -> float:
        if self.total == 0:
            return 0.0
        return self.total_duration_ms / self.total


@dataclass
class _LlmTaskStats:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class MetricsStore:
    lock: threading.Lock = field(default_factory=threading.Lock)
    http_total: int = 0
    http_errors: int = 0
    http_total_duration_ms: float = 0.0
    http_by_status: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    http_by_route: dict[str, _RouteStats] = field(default_factory=lambda: defaultdict(_RouteStats))
    celery_by_task: dict[str, _TaskStats] = field(default_factory=lambda: defaultdict(_TaskStats))
    llm_total_calls: int = 0
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    llm_by_task: dict[str, _LlmTaskStats] = field(default_factory=lambda: defaultdict(_LlmTaskStats))


_store = MetricsStore()


def record_http_request(*, method: str, path: str, status: int, duration_ms: float) -> None:
    route = f"{method} {normalize_path(path)}"
    is_error = status >= 500

    with _store.lock:
        _store.http_total += 1
        _store.http_total_duration_ms += duration_ms
        _store.http_by_status[str(status)] += 1
        if is_error:
            _store.http_errors += 1

        route_stats = _store.http_by_route[route]
        route_stats.count += 1
        route_stats.total_duration_ms += duration_ms
        if is_error:
            route_stats.error_count += 1


def record_celery_task(*, task_name: str, state: str, duration_ms: float) -> None:
    with _store.lock:
        stats = _store.celery_by_task[task_name]
        stats.total_duration_ms += duration_ms
        if state == "success":
            stats.success += 1
        elif state == "retry":
            stats.retry += 1
        else:
            stats.failure += 1


def record_llm_call(
    *,
    task: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> None:
    with _store.lock:
        _store.llm_total_calls += 1
        _store.llm_input_tokens += input_tokens
        _store.llm_output_tokens += output_tokens
        task_stats = _store.llm_by_task[task]
        task_stats.calls += 1
        task_stats.input_tokens += input_tokens
        task_stats.output_tokens += output_tokens


def is_slow_request(duration_ms: float) -> bool:
    return duration_ms >= _SLOW_REQUEST_MS


def uptime_seconds() -> float:
    return (datetime.now(UTC) - _PROCESS_STARTED_AT).total_seconds()


def get_summary(*, top_routes: int = 10, top_tasks: int = 10) -> dict[str, Any]:
    with _store.lock:
        avg_http_ms = (
            _store.http_total_duration_ms / _store.http_total if _store.http_total else 0.0
        )
        routes = sorted(
            (
                {
                    "route": route,
                    "count": stats.count,
                    "avg_duration_ms": round(stats.avg_duration_ms, 2),
                    "error_count": stats.error_count,
                }
                for route, stats in _store.http_by_route.items()
            ),
            key=lambda item: item["count"],
            reverse=True,
        )[:top_routes]

        celery = {
            name: {
                "success": stats.success,
                "failure": stats.failure,
                "retry": stats.retry,
                "avg_duration_ms": round(stats.avg_duration_ms, 2),
            }
            for name, stats in sorted(
                _store.celery_by_task.items(),
                key=lambda item: item[1].total,
                reverse=True,
            )[:top_tasks]
        }

        llm_by_task = {
            task: {
                "calls": stats.calls,
                "input_tokens": stats.input_tokens,
                "output_tokens": stats.output_tokens,
            }
            for task, stats in sorted(
                _store.llm_by_task.items(),
                key=lambda item: item[1].calls,
                reverse=True,
            )[:top_tasks]
        }

        return {
            "process": {
                "started_at": _PROCESS_STARTED_AT.isoformat(),
                "uptime_seconds": round(uptime_seconds(), 1),
            },
            "http": {
                "total_requests": _store.http_total,
                "error_requests": _store.http_errors,
                "avg_duration_ms": round(avg_http_ms, 2),
                "by_status": dict(_store.http_by_status),
                "top_routes": routes,
            },
            "celery": {
                "tasks": celery,
            },
            "llm": {
                "total_calls": _store.llm_total_calls,
                "total_input_tokens": _store.llm_input_tokens,
                "total_output_tokens": _store.llm_output_tokens,
                "by_task": llm_by_task,
            },
        }
