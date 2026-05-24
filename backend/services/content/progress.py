"""Redis-backed content generation progress for UI polling."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from config import get_settings

ACTIVE_KEY = "content_generation:active"
PROGRESS_PREFIX = "content_generation:progress:"
TTL_SECONDS = 86_400


def _progress_key(task_id: str) -> str:
    return f"{PROGRESS_PREFIX}{task_id}"


def _sync_client():
    import redis

    return redis.from_url(get_settings().redis_url, decode_responses=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        client.setex(_progress_key(task_id), TTL_SECONDS, json.dumps(payload))
        if payload.get("status") == "running":
            client.setex(ACTIVE_KEY, TTL_SECONDS, task_id)
        elif payload.get("status") in {"complete", "failed"}:
            if client.get(ACTIVE_KEY) == task_id:
                client.delete(ACTIVE_KEY)
    finally:
        client.close()


def progress_start(task_id: str, *, topic_id: str, topic_title: str) -> None:
    _write(
        task_id,
        {
            "task_id": task_id,
            "topic_id": topic_id,
            "topic_title": topic_title,
            "status": "running",
            "phase": "pairing",
            "percent": 5,
            "message": "Starting content generation…",
            "started_at": _now(),
            "finished_at": None,
            "result": None,
        },
    )


def progress_update(
    task_id: str,
    *,
    phase: str,
    percent: int,
    message: str,
    topic_id: str | None = None,
    topic_title: str | None = None,
) -> None:
    existing = _read(task_id) or {}
    payload = {
        "task_id": task_id,
        "topic_id": topic_id or existing.get("topic_id"),
        "topic_title": topic_title or existing.get("topic_title"),
        "status": "running",
        "phase": phase,
        "percent": percent,
        "message": message,
        "started_at": existing.get("started_at") or _now(),
        "finished_at": None,
        "result": None,
    }
    _write(task_id, payload)


def progress_finish(task_id: str, result: dict[str, Any]) -> None:
    existing = _read(task_id) or {}
    decision = result.get("decision", "content")
    _write(
        task_id,
        {
            "task_id": task_id,
            "topic_id": existing.get("topic_id"),
            "topic_title": existing.get("topic_title"),
            "status": "complete",
            "phase": "done",
            "percent": 100,
            "message": f"Content ready ({decision.replace('_', ' ')})",
            "started_at": existing.get("started_at"),
            "finished_at": _now(),
            "result": result,
        },
    )


def progress_fail(task_id: str, error: str) -> None:
    existing = _read(task_id) or {}
    _write(
        task_id,
        {
            "task_id": task_id,
            "topic_id": existing.get("topic_id"),
            "topic_title": existing.get("topic_title"),
            "status": "failed",
            "phase": "done",
            "percent": 100,
            "message": error[:500],
            "started_at": existing.get("started_at"),
            "finished_at": _now(),
            "result": {"status": "failed", "error": error},
        },
    )


async def get_progress(task_id: str | None = None) -> dict[str, Any] | None:
    import redis.asyncio as aioredis

    client = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        if not task_id:
            task_id = await client.get(ACTIVE_KEY)
        if not task_id:
            return None
        raw = await client.get(_progress_key(task_id))
        return json.loads(raw) if raw else None
    finally:
        await client.aclose()
