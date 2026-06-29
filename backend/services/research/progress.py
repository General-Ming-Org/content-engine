"""Redis-backed research sweep progress for UI polling."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from config import get_settings

PROGRESS_PREFIX = "research_sweep:progress:"
TTL_SECONDS = 86_400


def _active_key(user_id: str) -> str:
    return f"research_sweep:active:{user_id}"


def _progress_key(task_id: str) -> str:
    return f"{PROGRESS_PREFIX}{task_id}"


def _sync_client():
    import redis

    return redis.from_url(get_settings().redis_url, decode_responses=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _percent(current: int, total: int, *, floor: int = 0, ceiling: int = 100) -> int:
    if total <= 0:
        return ceiling if current > 0 else floor
    raw = floor + int((current / total) * (ceiling - floor))
    return min(ceiling, max(floor, raw))


def _read(task_id: str) -> dict[str, Any] | None:
    client = _sync_client()
    try:
        raw = client.get(_progress_key(task_id))
        return json.loads(raw) if raw else None
    finally:
        client.close()


def _write(task_id: str, payload: dict[str, Any]) -> None:
    client = _sync_client()
    try:
        key = _progress_key(task_id)
        client.setex(key, TTL_SECONDS, json.dumps(payload))
        user_id = payload.get("user_id")
        if user_id and payload.get("status") == "running":
            client.setex(_active_key(str(user_id)), TTL_SECONDS, task_id)
        elif user_id and payload.get("status") in {"complete", "failed", "blocked"}:
            active = client.get(_active_key(str(user_id)))
            if active == task_id:
                client.delete(_active_key(str(user_id)))
    finally:
        client.close()


def progress_start(task_id: str, user_id: UUID | str) -> None:
    _write(
        task_id,
        {
            "task_id": task_id,
            "user_id": str(user_id),
            "status": "running",
            "phase": "searching",
            "current": 0,
            "total": 0,
            "percent": 5,
            "message": "Searching across research domains…",
            "started_at": _now(),
            "finished_at": None,
            "result": None,
        },
    )


def progress_searching(task_id: str, user_id: UUID | str) -> None:
    _write(
        task_id,
        {
            "task_id": task_id,
            "user_id": str(user_id),
            "status": "running",
            "phase": "searching",
            "current": 0,
            "total": 0,
            "percent": 10,
            "message": "Searching across research domains…",
            "started_at": _now(),
            "finished_at": None,
            "result": None,
        },
    )


def progress_enriching(task_id: str, *, current: int, total: int, topic_title: str | None = None) -> None:
    existing = _read(task_id) or {}
    label = topic_title[:80] if topic_title else f"topic {current} of {total}"
    _write(
        task_id,
        {
            **existing,
            "task_id": task_id,
            "status": "running",
            "phase": "enriching",
            "current": current,
            "total": total,
            "percent": _percent(current, total, floor=15, ceiling=95),
            "message": f"Synthesizing {label}…",
            "finished_at": None,
            "result": None,
        },
    )


def progress_finish(task_id: str, result: dict[str, Any]) -> None:
    existing = _read(task_id) or {}
    status = result.get("status", "complete")
    stored = int(result.get("results_stored", 0) or 0)
    found = int(result.get("results_found", 0) or 0)
    skipped = int(result.get("results_skipped", 0) or 0)

    if status == "blocked":
        ui_status = "blocked"
        message = result.get("message") or result.get("reason") or "Research sweep was blocked."
    elif found > 0 and stored == 0:
        ui_status = "failed"
        message = f"Found {found} topics but stored none ({skipped} skipped)."
    elif found == 0:
        ui_status = "failed"
        message = "No topics found from search."
    else:
        ui_status = "complete"
        message = f"Stored {stored} of {found} topics."

    _write(
        task_id,
        {
            **existing,
            "task_id": task_id,
            "status": ui_status,
            "phase": "done",
            "current": stored,
            "total": found,
            "percent": 100,
            "message": message,
            "finished_at": _now(),
            "result": result,
        },
    )


def progress_fail(task_id: str, error: str, user_id: UUID | str | None = None) -> None:
    existing = _read(task_id) or {}
    _write(
        task_id,
        {
            **existing,
            "task_id": task_id,
            "user_id": str(user_id) if user_id else existing.get("user_id"),
            "status": "failed",
            "phase": "done",
            "current": 0,
            "total": 0,
            "percent": 100,
            "message": error,
            "started_at": existing.get("started_at"),
            "finished_at": _now(),
            "result": {"status": "failed", "error": error},
        },
    )


async def get_progress(
    task_id: str | None = None,
    *,
    user_id: str | None = None,
) -> dict[str, Any] | None:
    import redis.asyncio as aioredis

    client = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        if not task_id and user_id:
            task_id = await client.get(_active_key(user_id))
        if not task_id:
            return None
        raw = await client.get(_progress_key(task_id))
        if not raw:
            return None
        return json.loads(raw)
    finally:
        await client.aclose()
