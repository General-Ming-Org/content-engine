"""AI model status endpoints.

Model selection is intentionally not managed through the database or per-task
overrides. Operators configure exactly one provider/model pair in `.env`:

    LLM_PROVIDER=anthropic
    LLM_MODEL=claude-sonnet-4-6
"""
from typing import Any

import structlog
from fastapi import APIRouter, Depends

from config import get_settings
from models.user import User
from services.ai.providers import CATALOG, get_info
from services.auth.deps import get_current_user

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("")
async def list_models(
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the configured model and the optional catalogue for UI hints."""
    settings = get_settings()
    provider = settings.llm_provider.strip().strip("/")
    model = settings.llm_model.strip().strip("/")
    model_id = f"{provider}/{model}" if provider and model else ""
    return {
        "provider": provider,
        "model": model,
        "model_id": model_id,
        "configured": bool(provider and model),
        "info": (info.to_dict() if model_id and (info := get_info(model_id)) else None),
        "catalog": [m.to_dict() for m in CATALOG],
    }
