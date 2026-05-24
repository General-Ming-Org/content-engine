"""Admin user management endpoints. All require admin role."""
from datetime import datetime
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from services.auth.deps import require_admin

logger = structlog.get_logger(__name__)
router = APIRouter()


class UserListItem(BaseModel):
    id: str
    email: str
    name: str | None
    role: str
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class UpdateRoleRequest(BaseModel):
    role: str = Field(pattern=r"^(admin|user)$")


@router.get("", response_model=list[UserListItem])
async def list_users(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[UserListItem]:
    users = (await db.execute(select(User).order_by(User.created_at.desc()))).scalars().all()
    return [
        UserListItem(
            id=str(u.id),
            email=u.email,
            name=u.name,
            role=u.role,
            is_active=u.is_active,
            last_login_at=u.last_login_at,
            created_at=u.created_at,
        )
        for u in users
    ]


@router.patch("/{user_id}/role", response_model=UserListItem)
async def update_role(
    user_id: UUID,
    payload: UpdateRoleRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> UserListItem:
    if user_id == admin.id and payload.role != "admin":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Can't demote yourself")

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    user.role = payload.role
    await db.commit()
    logger.info("user_role_changed", target=str(user_id), role=payload.role, by=str(admin.id))
    return UserListItem(
        id=str(user.id), email=user.email, name=user.name, role=user.role,
        is_active=user.is_active, last_login_at=user.last_login_at, created_at=user.created_at,
    )


@router.patch("/{user_id}/active")
async def set_active(
    user_id: UUID,
    payload: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if user_id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Can't disable yourself")
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    user.is_active = bool(payload.get("is_active", True))
    await db.commit()
    return {"id": str(user.id), "is_active": user.is_active}


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Hard delete. Cascades to all per-user rows (posts, articles, etc.)."""
    if user_id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Can't delete yourself")
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        return
    await db.delete(user)
    await db.commit()
    logger.warning("user_deleted", user_id=str(user_id), by=str(admin.id))
