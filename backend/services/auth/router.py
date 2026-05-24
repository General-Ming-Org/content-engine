"""Auth endpoints: signup, login, /me, password change, email verification."""
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from services.auth.deps import get_current_user
from services.auth.email_verification import (
    can_resend,
    consume_verification_token,
    issue_verification_token,
    send_verification_email,
)
from services.auth.jwt import create_access_token
from services.auth.password import hash_password, verify_password

logger = structlog.get_logger(__name__)
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────
class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    password_confirm: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be blank.")
        return v

    @model_validator(mode="after")
    def _passwords_match(self) -> "SignupRequest":
        if self.password != self.password_confirm:
            raise ValueError("Passwords do not match.")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: dict


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    is_active: bool
    email_verified: bool


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=8)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _public_origin(request: Request) -> str:
    """Build email links without an env var.

    Browser signup/resend requests include Origin. If a reverse proxy is in
    front, X-Forwarded-* headers are respected. Local dev falls back to the Vite
    origin.
    """
    origin = request.headers.get("origin")
    if origin:
        return origin.rstrip("/")

    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_proto and forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}".rstrip("/")

    host = request.headers.get("host")
    if host and not host.startswith("backend:") and not host.startswith("localhost:8000"):
        return f"{request.url.scheme}://{host}".rstrip("/")

    return "http://localhost:3000"


def _serialize(u: User) -> dict:
    return {
        "id": str(u.id),
        "email": u.email,
        "name": u.name,
        "role": u.role,
        "is_active": u.is_active,
        "email_verified": u.email_verified_at is not None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.post("/signup", response_model=TokenResponse)
async def signup(
    request: Request,
    payload: SignupRequest,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Register a new account. First *active* account becomes admin."""
    existing = (
        await db.execute(select(User).where(User.email == payload.email.lower()))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")

    # Ignore inactive seed/legacy accounts (e.g. `legacy@content-engine.local`
    # created by migration 003) so the first real signup still becomes admin.
    active_count = (
        await db.execute(select(func.count(User.id)).where(User.is_active.is_(True)))
    ).scalar_one()
    role = "admin" if active_count == 0 else "user"

    user = User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        name=payload.name,
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info("user_signup", user_id=str(user.id), role=role)

    raw_token = await issue_verification_token(db, user)
    background.add_task(send_verification_email, user, raw_token, _public_origin(request))

    access_token, exp = create_access_token(user.id, user.role)
    return TokenResponse(access_token=access_token, expires_at=exp, user=_serialize(user))


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = (
        await db.execute(select(User).where(User.email == payload.email.lower()))
    ).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        # Same message for "wrong email" and "wrong password" to avoid
        # email-enumeration leaks.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Email or password is incorrect.",
        )
    if not user.is_active:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "This account has been disabled. Contact an administrator.",
        )

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    access_token, exp = create_access_token(user.id, user.role)
    return TokenResponse(access_token=access_token, expires_at=exp, user=_serialize(user))


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(**_serialize(user))


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Current password is incorrect.",
        )
    user.password_hash = hash_password(body.new_password)
    await db.commit()


@router.post("/verify-email", response_model=UserResponse)
async def verify_email(payload: VerifyEmailRequest, db: AsyncSession = Depends(get_db)) -> UserResponse:
    try:
        user = await consume_verification_token(db, payload.token)
    except ValueError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This verification link is invalid or has expired. Request a new one.",
        )
    return UserResponse(**_serialize(user))


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(
    request: Request,
    payload: ResendVerificationRequest,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Resend the verification email. Always returns 202 to avoid leaking
    which emails are registered."""
    from services.auth.email_verification import RESEND_COOLDOWN_SECONDS
    from services.common.rate_limit import enforce_rate_limit

    generic = {"detail": "If an account exists for that email, a new verification message has been sent."}
    email = payload.email.lower()

    # Per-email Redis lock stops parallel clicks from queuing multiple sends.
    await enforce_rate_limit(
        f"auth:resend-verify:email:{email}",
        RESEND_COOLDOWN_SECONDS,
        message="Please wait a moment before requesting another verification email.",
    )

    user = (
        await db.execute(
            select(User).where(User.email == email).with_for_update()
        )
    ).scalar_one_or_none()
    if user is None or user.email_verified_at is not None:
        return generic
    if not can_resend(user):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Please wait a moment before requesting another verification email.",
            headers={"Retry-After": str(RESEND_COOLDOWN_SECONDS)},
        )
    raw_token = await issue_verification_token(db, user)
    background.add_task(send_verification_email, user, raw_token, _public_origin(request))
    return generic
