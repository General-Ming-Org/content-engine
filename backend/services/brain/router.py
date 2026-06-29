"""Research Brain API routes."""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from models.user import User
from services.auth.deps import get_current_user, require_admin

router = APIRouter()


class PersonalityBioUpdate(BaseModel):
    bio_context: str | None = None
    focus_areas: list[str] | None = None


@router.get("/inspiration")
async def list_inspiration_posts(
    domain: str | None = Query(None),
    min_traction: float = Query(0.0),
    limit: int = Query(20, le=50),
    _: User = Depends(get_current_user),
) -> dict[str, Any]:
    from services.brain.style_brief import list_inspiration

    posts = await list_inspiration(domain=domain, min_traction=min_traction, limit=limit)
    return {"posts": posts}


@router.post("/inspiration/harvest")
async def trigger_harvest(_: User = Depends(require_admin)) -> dict[str, Any]:
    from services.brain.signal_harvester import harvest_signals

    return await harvest_signals()


@router.get("/personality")
async def get_personality(user: User = Depends(get_current_user)) -> dict[str, Any]:
    from services.brain.personality import get_profile_dict

    return await get_profile_dict(user.id)


@router.put("/personality/bio")
async def update_personality_bio(
    body: PersonalityBioUpdate,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    from services.brain.personality import get_profile_dict, update_profile_bio

    await update_profile_bio(user.id, body.bio_context, body.focus_areas)
    return await get_profile_dict(user.id)


@router.get("/insights")
async def get_insights(user: User = Depends(get_current_user)) -> dict[str, Any]:
    from services.brain.personality import get_profile_dict

    profile = await get_profile_dict(user.id)
    return {"insights": profile.get("insights") or {}}


@router.post("/personality/refresh")
async def refresh_personality(user: User = Depends(get_current_user)) -> dict[str, Any]:
    from services.brain.personality import refresh_profile

    return await refresh_profile(user.id)
