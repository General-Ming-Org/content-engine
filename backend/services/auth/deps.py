"""FastAPI dependencies for authenticated routes."""
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from services.auth.jwt import decode_token

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the User from the Bearer token. 401 if missing / invalid / disabled."""
    if not credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing authorization")
    try:
        payload = decode_token(credentials.credentials)
        user_id = UUID(payload["sub"])
    except (ValueError, KeyError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc))

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or disabled")
    return user


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Same as get_current_user but returns None instead of raising."""
    if not credentials:
        return None
    try:
        payload = decode_token(credentials.credentials)
        user_id = UUID(payload["sub"])
    except (ValueError, KeyError):
        return None
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    return user if user and user.is_active else None


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin role required")
    return user


async def require_verified_user(user: User = Depends(get_current_user)) -> User:
    """Hard gate for application routes after signup/login.

    Auth routes stay available so an unverified user can sign in, resend the
    verification email, and consume the verification token. Everything else
    requires a confirmed email address.
    """
    if user.email_verified_at is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Please verify your email before using Content Engine.",
        )
    return user
