"""Per-user settings CRUD — manages user_settings table entries scoped to the caller.

The embedding model is a system-wide config (EMBEDDING_PROVIDER + EMBEDDING_MODEL
in .env), not a per-user setting — see services/ai/embeddings.py. User-scoped keys
here are things like posting cadence, voice preferences, and the LinkedIn OAuth
redirect mode.
"""
from typing import Any

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.settings import UserSetting
from models.user import User
from services.auth.deps import get_current_user

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("")
async def get_all_settings(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    results = (
        await db.execute(select(UserSetting).where(UserSetting.user_id == user.id))
    ).scalars().all()
    return {s.key: s.value for s in results}


@router.put("/{key}")
async def update_setting(
    key: str,
    payload: dict[str, Any],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    setting = (
        await db.execute(
            select(UserSetting).where(
                UserSetting.user_id == user.id,
                UserSetting.key == key,
            )
        )
    ).scalar_one_or_none()
    if setting:
        setting.value = payload
    else:
        setting = UserSetting(user_id=user.id, key=key, value=payload)
        db.add(setting)
    await db.commit()
    return {"key": key, "value": setting.value}
