"""Observability API — in-process metrics summary for operators."""
from __future__ import annotations

from fastapi import APIRouter

from config import get_settings
from services.observability.metrics import get_summary
from services.observability.stack import get_stack_status

router = APIRouter()


@router.get("/summary")
async def observability_summary() -> dict:
    """Rolling counters for HTTP traffic, Celery tasks, and LLM usage in this process."""
    settings = get_settings()
    return {
        "service": "content-engine-api",
        "env": settings.app_env,
        "version": "0.1.0",
        "metrics": get_summary(),
    }


@router.get("/stack")
async def observability_stack() -> dict:
    """Live status of docker-compose services, Celery workers, and host metadata."""
    return await get_stack_status()
