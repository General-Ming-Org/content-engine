"""Read container status from the host Docker socket (optional, read-only mount)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

DOCKER_SOCKET = Path("/var/run/docker.sock")


async def list_containers() -> list[dict[str, Any]]:
    """Return running containers when /var/run/docker.sock is mounted."""
    if not DOCKER_SOCKET.is_socket():
        return []

    try:
        transport = httpx.AsyncHTTPTransport(uds=str(DOCKER_SOCKET))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://docker",
            timeout=3.0,
        ) as client:
            response = await client.get("/containers/json", params={"all": "true"})
        response.raise_for_status()
        raw = response.json()
    except Exception as exc:
        logger.warning("docker_socket_list_failed", error=str(exc))
        return []

    containers: list[dict[str, Any]] = []
    for item in raw:
        names = [name.lstrip("/") for name in item.get("Names", [])]
        labels = item.get("Labels") or {}
        compose_service = labels.get("com.docker.compose.service")
        health = (item.get("Status") or "").lower()
        health_state = None
        if "healthy" in health:
            health_state = "healthy"
        elif "unhealthy" in health:
            health_state = "unhealthy"

        containers.append(
            {
                "id": item.get("Id", "")[:12],
                "name": names[0] if names else item.get("Id", "")[:12],
                "names": names,
                "image": item.get("Image"),
                "state": item.get("State"),
                "status": item.get("Status"),
                "health": health_state,
                "compose_project": labels.get("com.docker.compose.project"),
                "compose_service": [compose_service] if compose_service else [],
                "created": item.get("Created"),
            }
        )

    containers.sort(key=lambda c: (c.get("compose_service") or [c["name"]])[0])
    return containers
