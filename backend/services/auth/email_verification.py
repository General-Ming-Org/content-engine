"""Email-verification token generation, sending, and validation.

Design:
  - Raw token is a 32-byte URL-safe random string. Only its SHA-256 hash is
    persisted; the raw token leaves the server exactly once, in the email.
  - Tokens expire after VERIFICATION_TTL_HOURS to bound damage from leaked
    email archives.
  - Verification is blocking for application routes; auth routes remain open
    so users can sign in, request a new link, and consume the token.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import aiosmtplib
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.user import User
from services.notifications.email_branding import build_branded_message

logger = structlog.get_logger(__name__)
settings = get_settings()

VERIFICATION_TTL_HOURS = 24
RESEND_COOLDOWN_SECONDS = 120


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def issue_verification_token(db: AsyncSession, user: User) -> str:
    """Generate a fresh token, persist its hash, return the RAW token for emailing."""
    raw = secrets.token_urlsafe(32)
    user.email_verification_token_hash = _hash(raw)
    user.email_verification_sent_at = datetime.now(timezone.utc)
    await db.commit()
    return raw


async def send_verification_email(user: User, raw_token: str, public_base_url: str) -> None:
    """Send the verification email. Silently skipped when SMTP is unconfigured
    (logged at WARNING so it's visible in dev without crashing signup)."""
    if not all([settings.effective_smtp_host, settings.smtp_username, settings.smtp_password]):
        logger.warning(
            "verification_email_skipped_smtp_not_configured",
            user_id=str(user.id),
        )
        return

    verify_link = f"{public_base_url.rstrip('/')}/verify-email?token={raw_token}"
    subject = "Verify your Content Engine email"
    text_body = (
        f"Hi {user.name},\n\n"
        f"Please confirm your email address by clicking the link below:\n\n"
        f"  {verify_link}\n\n"
        f"This link expires in {VERIFICATION_TTL_HOURS} hours. "
        f"If you didn't create an account, you can safely ignore this message.\n\n"
        f"— Content Engine"
    )
    html_inner = f"""
      <p style="margin:0 0 16px">Hi {user.name}, please verify the email address you used to sign up.</p>
      <p style="margin:0 0 8px;color:#888;font-size:13px">Or copy this link into your browser:</p>
      <p style="margin:0;color:#5b5bd6;font-size:13px;word-break:break-all">{verify_link}</p>
      <p style="margin:24px 0 0;color:#aaa;font-size:12px">
        This link expires in {VERIFICATION_TTL_HOURS} hours. If you didn't create this account, ignore this email.
      </p>
    """

    msg = build_branded_message(
        to_address=user.email,
        subject=subject,
        plain_body=text_body,
        html_inner=html_inner,
        title="Confirm your email",
        cta_url=verify_link,
        cta_label="Verify email",
    )

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.effective_smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            start_tls=True,
        )
        logger.info("verification_email_sent", user_id=str(user.id))
    except Exception as exc:
        logger.error("verification_email_failed", user_id=str(user.id), error=str(exc))
        raise


async def consume_verification_token(db: AsyncSession, raw_token: str) -> User:
    """Validate a token, mark the user verified, clear the token. Raises ValueError on failure."""
    token_hash = _hash(raw_token)
    user = (
        await db.execute(
            select(User).where(User.email_verification_token_hash == token_hash)
        )
    ).scalar_one_or_none()
    if user is None:
        raise ValueError("invalid_or_expired_token")

    sent_at = user.email_verification_sent_at
    if sent_at is None or datetime.now(timezone.utc) - sent_at > timedelta(
        hours=VERIFICATION_TTL_HOURS
    ):
        # Clear the stale token so it can't be retried.
        user.email_verification_token_hash = None
        await db.commit()
        raise ValueError("invalid_or_expired_token")

    user.email_verified_at = datetime.now(timezone.utc)
    user.email_verification_token_hash = None
    await db.commit()
    logger.info("user_email_verified", user_id=str(user.id))
    return user


def can_resend(user: User) -> bool:
    """Rate-limit resends to one per minute per account."""
    if user.email_verification_sent_at is None:
        return True
    return (
        datetime.now(timezone.utc) - user.email_verification_sent_at
    ).total_seconds() >= RESEND_COOLDOWN_SECONDS
