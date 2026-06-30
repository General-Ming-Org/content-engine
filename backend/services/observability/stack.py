"""Collect live status of the docker-compose stack and background workers."""
from __future__ import annotations

import asyncio
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import structlog

from config import get_settings
from database import check_db_connection
from services.observability.docker_containers import list_containers

logger = structlog.get_logger(__name__)

DOCKER_SOCKET = Path("/var/run/docker.sock")

# Compose service names we expect in a full deployment.
_EXPECTED_SERVICES: tuple[dict[str, str], ...] = (
    {"name": "backend", "role": "api"},
    {"name": "worker", "role": "celery_worker"},
    {"name": "beat", "role": "celery_beat"},
    {"name": "frontend", "role": "web"},
    {"name": "db", "role": "postgres"},
    {"name": "redis", "role": "cache"},
    {"name": "qdrant", "role": "vector_db"},
    {"name": "knowledge-mcp", "role": "mcp"},
    {"name": "tavily-mcp", "role": "mcp"},
    {"name": "nginx", "role": "proxy"},
    {"name": "certbot", "role": "tls"},
)


async def get_stack_status() -> dict[str, Any]:
    """Return a snapshot of what should be running and whether it responds."""
    settings = get_settings()

    probes = await asyncio.gather(
        _probe_postgres(),
        _probe_redis(settings.redis_url),
        _probe_http("qdrant", f"{settings.qdrant_url.rstrip('/')}/readyz"),
        _probe_http("knowledge-mcp", settings.mcp_knowledge_url),
        _probe_http("tavily-mcp", settings.mcp_tavily_url),
        _probe_http("frontend", "http://frontend:3000"),
        _probe_tcp("nginx", "nginx", 80),
        _celery_status(),
        _redis_queues(settings.redis_url),
        _gcp_metadata(),
        return_exceptions=True,
    )

    (
        postgres,
        redis_probe,
        qdrant,
        knowledge_mcp,
        tavily_mcp,
        frontend,
        nginx,
        celery,
        queues,
        host,
    ) = [_unwrap(item) for item in probes]

    containers = await list_containers()
    probe_map = {
        "db": postgres,
        "redis": redis_probe,
        "qdrant": qdrant,
        "knowledge-mcp": knowledge_mcp,
        "tavily-mcp": tavily_mcp,
        "frontend": frontend,
        "nginx": nginx,
    }
    services = _merge_service_status(
        containers=containers,
        probes=probe_map,
        celery=celery,
        queues=queues,
    )

    overall = "ok"
    if any(s["status"] in ("down", "error") for s in services if s["required"]):
        overall = "degraded"
    if celery.get("workers_online", 0) == 0:
        overall = "degraded"

    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "overall": overall,
        "host": host,
        "docker": {
            "socket_available": DOCKER_SOCKET.is_socket(),
            "containers": containers,
        },
        "services": services,
        "celery": celery,
        "queues": queues,
    }


def _unwrap(value: Any) -> Any:
    if isinstance(value, Exception):
        logger.warning("stack_probe_failed", error=str(value))
        return {"status": "error", "detail": type(value).__name__}
    return value


async def _probe_postgres() -> dict[str, Any]:
    ok = await check_db_connection()
    return {"status": "ok" if ok else "down"}


async def _probe_redis(redis_url: str) -> dict[str, Any]:
    import redis.asyncio as aioredis

    client = aioredis.from_url(redis_url, decode_responses=True)
    try:
        pong = await client.ping()
        return {"status": "ok" if pong else "down"}
    except Exception as exc:
        return {"status": "down", "detail": type(exc).__name__}
    finally:
        await client.aclose()


async def _probe_http(name: str, url: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=3.0, follow_redirects=True) as client:
            response = await client.get(url)
        if response.status_code < 500:
            return {"status": "ok", "http_status": response.status_code}
        return {"status": "degraded", "http_status": response.status_code}
    except httpx.ConnectError:
        return {"status": "down", "detail": "connection_refused"}
    except Exception as exc:
        return {"status": "error", "detail": type(exc).__name__}


async def _probe_tcp(name: str, host: str, port: int) -> dict[str, Any]:
    def _check() -> bool:
        with socket.create_connection((host, port), timeout=2.0):
            return True

    try:
        await asyncio.to_thread(_check)
        return {"status": "ok"}
    except OSError:
        return {"status": "down", "detail": "connection_refused"}


async def _celery_status() -> dict[str, Any]:
    def _inspect() -> dict[str, Any]:
        from services.scheduler.tasks import celery_app

        inspector = celery_app.control.inspect(timeout=2.0)
        ping = inspector.ping() or {}
        stats = inspector.stats() or {}
        active = inspector.active() or {}
        registered = inspector.registered() or {}

        worker_names = sorted(ping.keys())
        active_tasks = sum(len(tasks) for tasks in active.values())
        registered_tasks = {
            worker: len(tasks) for worker, tasks in registered.items()
        }

        return {
            "workers_online": len(worker_names),
            "worker_names": worker_names,
            "active_tasks": active_tasks,
            "registered_tasks": registered_tasks,
            "stats": {
                name: {
                    "pool_max_concurrency": data.get("pool", {}).get("max-concurrency"),
                    "total_tasks": data.get("total", {}),
                }
                for name, data in stats.items()
            },
        }

    try:
        return await asyncio.to_thread(_inspect)
    except Exception as exc:
        return {
            "workers_online": 0,
            "worker_names": [],
            "active_tasks": 0,
            "registered_tasks": {},
            "stats": {},
            "status": "error",
            "detail": type(exc).__name__,
        }


async def _redis_queues(redis_url: str) -> dict[str, Any]:
    import redis.asyncio as aioredis

    client = aioredis.from_url(redis_url, decode_responses=True)
    try:
        default_depth = await client.llen("celery")
        beat_lock = await client.get("redbeat::lock")
        redbeat_keys = []
        async for key in client.scan_iter("redbeat:*", count=100):
            redbeat_keys.append(key)
            if len(redbeat_keys) >= 20:
                break

        return {
            "celery_default_depth": default_depth,
            "beat_lock_present": beat_lock is not None,
            "redbeat_schedule_keys": len(redbeat_keys),
        }
    except Exception as exc:
        return {"status": "error", "detail": type(exc).__name__}
    finally:
        await client.aclose()


async def _gcp_metadata() -> dict[str, Any]:
    metadata_url = "http://metadata.google.internal/computeMetadata/v1"
    headers = {"Metadata-Flavor": "Google"}

    async def _get(path: str) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                response = await client.get(f"{metadata_url}/{path}", headers=headers)
            if response.status_code == 200:
                return response.text.strip()
        except Exception:
            return None
        return None

    name, zone, machine_type, project = await asyncio.gather(
        _get("instance/name"),
        _get("instance/zone"),
        _get("instance/machine-type"),
        _get("project/project-id"),
    )

    if not name:
        return {"platform": "local"}

    zone_short = zone.split("/")[-1] if zone else None
    machine_short = machine_type.split("/")[-1] if machine_type else None
    return {
        "platform": "gcp",
        "instance": name,
        "zone": zone_short,
        "machine_type": machine_short,
        "project": project,
    }


def _merge_service_status(
    *,
    containers: list[dict[str, Any]],
    probes: dict[str, dict[str, Any]],
    celery: dict[str, Any],
    queues: dict[str, Any],
) -> list[dict[str, Any]]:
    by_compose_name = _index_containers(containers)
    merged: list[dict[str, Any]] = []

    for expected in _EXPECTED_SERVICES:
        name = expected["name"]
        role = expected["role"]
        container = by_compose_name.get(name)
        probe = probes.get(name)

        status = _derive_status(name, role, container, probe, celery, queues)
        merged.append(
            {
                "name": name,
                "role": role,
                "required": name not in ("nginx", "certbot"),
                "status": status,
                "container": container,
                "probe": probe,
            }
        )

    return merged


def _index_containers(containers: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for container in containers:
        for label in container.get("compose_service", []):
            indexed[label] = container
        # Fallback: match by container name suffix
        for expected in _EXPECTED_SERVICES:
            if expected["name"] in container.get("name", ""):
                indexed.setdefault(expected["name"], container)
    return indexed


def _derive_status(
    name: str,
    role: str,
    container: dict[str, Any] | None,
    probe: dict[str, Any] | None,
    celery: dict[str, Any],
    queues: dict[str, Any],
) -> str:
    if role == "celery_worker":
        if celery.get("workers_online", 0) > 0:
            return "running"
        if container and container.get("state") == "running":
            return "degraded"
        return "down"

    if role == "celery_beat":
        if queues.get("beat_lock_present"):
            return "running"
        if container and container.get("state") == "running":
            return "running"
        return "down"

    if role == "api" and name == "backend":
        return "running"

    if probe and probe.get("status") == "ok":
        return "running"

    if container:
        state = container.get("state", "unknown")
        health = container.get("health")
        if state == "running" and health in (None, "healthy"):
            return "running"
        if state == "running":
            return "degraded"
        return "down"

    if probe and probe.get("status") == "down":
        return "down"

    return "unknown"
