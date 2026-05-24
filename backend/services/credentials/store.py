"""DB operations for per-user platform credentials.

LinkedIn OAuth tokens:
    secret_payload     = encrypted {access_token, refresh_token}
    metadata_payload   = {person_urn, scope, expires_at, ...}

LinkedIn Developer App (per user — replaces env LINKEDIN_CLIENT_*):
    secret_payload     = encrypted {client_secret}
    metadata_payload   = {client_id}

Substack:
    secret_payload     = encrypted {email, password}
    metadata_payload   = {publication_url}

SMTP:
    secret_payload     = encrypted {smtp_to_address}  # operator runs the SMTP server, user owns recipient
    metadata_payload   = {}
"""
from datetime import datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import AsyncSessionLocal
from models.user_credentials import UserCredential
from services.auth.crypto import decrypt, encrypt

logger = structlog.get_logger(__name__)


async def _upsert(
    db: AsyncSession,
    user_id: UUID,
    provider: str,
    secret: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
) -> UserCredential:
    existing = (
        await db.execute(
            select(UserCredential).where(
                UserCredential.user_id == user_id,
                UserCredential.provider == provider,
            )
        )
    ).scalar_one_or_none()

    cipher = encrypt(secret) if secret is not None else None

    if existing:
        if cipher is not None:
            existing.secret_payload = cipher
        if metadata is not None:
            existing.metadata_payload = metadata
        return existing

    record = UserCredential(
        user_id=user_id,
        provider=provider,
        secret_payload=cipher,
        metadata_payload=metadata,
    )
    db.add(record)
    return record


async def save_linkedin_app_credential(
    user_id: UUID,
    client_id: str,
    client_secret: str,
) -> None:
    async with AsyncSessionLocal() as db:
        await _upsert(
            db,
            user_id,
            "linkedin_app",
            secret={"client_secret": client_secret},
            metadata={"client_id": client_id.strip()},
        )
        await db.commit()
    logger.info("linkedin_app_cred_saved", user_id=str(user_id))


async def get_linkedin_app_credential(user_id: UUID) -> dict[str, str] | None:
    async with AsyncSessionLocal() as db:
        record = (
            await db.execute(
                select(UserCredential).where(
                    UserCredential.user_id == user_id,
                    UserCredential.provider == "linkedin_app",
                )
            )
        ).scalar_one_or_none()
    if not record or not record.secret_payload:
        return None
    secret = decrypt(record.secret_payload)
    client_id = (record.metadata_payload or {}).get("client_id", "")
    client_secret = secret.get("client_secret", "") if isinstance(secret, dict) else ""
    if not client_id or not client_secret:
        return None
    return {"client_id": client_id, "client_secret": client_secret}


async def resolve_linkedin_app_credentials(user_id: UUID) -> tuple[str, str] | None:
    """Per-user Developer App creds, with optional env fallback for legacy deploys."""
    cred = await get_linkedin_app_credential(user_id)
    if cred:
        return cred["client_id"], cred["client_secret"]

    from config import get_settings

    s = get_settings()
    if s.linkedin_client_id and s.linkedin_client_secret:
        return s.linkedin_client_id, s.linkedin_client_secret
    return None


async def save_linkedin_credential(
    user_id: UUID,
    access_token: str,
    refresh_token: str,
    person_urn: str,
    expires_at: datetime | None = None,
) -> None:
    async with AsyncSessionLocal() as db:
        await _upsert(
            db, user_id, "linkedin",
            secret={"access_token": access_token, "refresh_token": refresh_token},
            metadata={
                "person_urn": person_urn,
                "expires_at": expires_at.isoformat() if expires_at else None,
            },
        )
        await db.commit()
    logger.info("linkedin_cred_saved", user_id=str(user_id))


async def get_linkedin_credential(user_id: UUID) -> dict[str, Any] | None:
    """Returns {access_token, refresh_token, person_urn, expires_at} or None."""
    async with AsyncSessionLocal() as db:
        record = (
            await db.execute(
                select(UserCredential).where(
                    UserCredential.user_id == user_id,
                    UserCredential.provider == "linkedin",
                )
            )
        ).scalar_one_or_none()
    if not record or not record.secret_payload:
        return None
    secret = decrypt(record.secret_payload)
    return {
        "access_token": secret.get("access_token"),
        "refresh_token": secret.get("refresh_token"),
        "person_urn": (record.metadata_payload or {}).get("person_urn"),
        "expires_at": (record.metadata_payload or {}).get("expires_at"),
    }


async def save_substack_credential(
    user_id: UUID,
    email: str,
    password: str,
    publication_url: str,
) -> None:
    async with AsyncSessionLocal() as db:
        await _upsert(
            db, user_id, "substack",
            secret={"email": email, "password": password},
            metadata={"publication_url": publication_url},
        )
        await db.commit()
    logger.info("substack_cred_saved", user_id=str(user_id))


async def get_substack_credential(user_id: UUID) -> dict[str, Any] | None:
    async with AsyncSessionLocal() as db:
        record = (
            await db.execute(
                select(UserCredential).where(
                    UserCredential.user_id == user_id,
                    UserCredential.provider == "substack",
                )
            )
        ).scalar_one_or_none()
    if not record or not record.secret_payload:
        return None
    secret = decrypt(record.secret_payload)
    return {
        "email": secret.get("email"),
        "password": secret.get("password"),
        "publication_url": (record.metadata_payload or {}).get("publication_url"),
    }


async def save_smtp_to(user_id: UUID, to_address: str) -> None:
    async with AsyncSessionLocal() as db:
        await _upsert(
            db, user_id, "smtp",
            secret={"to_address": to_address},
            metadata={},
        )
        await db.commit()


async def get_smtp_to_address(user_id: UUID) -> str | None:
    """Explicit digest override saved in credentials (optional)."""
    async with AsyncSessionLocal() as db:
        record = (
            await db.execute(
                select(UserCredential).where(
                    UserCredential.user_id == user_id,
                    UserCredential.provider == "smtp",
                )
            )
        ).scalar_one_or_none()
    if not record or not record.secret_payload:
        return None
    secret = decrypt(record.secret_payload)
    address = secret.get("to_address") if isinstance(secret, dict) else None
    return address.strip() if isinstance(address, str) and address.strip() else None


async def resolve_digest_recipient(user_id: UUID) -> str | None:
    """Where to send digests and alert emails for this user.

    Uses an optional per-user override; otherwise the account login email.
    """
    override = await get_smtp_to_address(user_id)
    if override:
        return override

    from models.user import User

    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()
    if not user or not user.is_active:
        return None
    email = (user.email or "").strip()
    if email and "@" in email:
        return email
    return None


async def delete_credential(user_id: UUID, provider: str) -> bool:
    async with AsyncSessionLocal() as db:
        record = (
            await db.execute(
                select(UserCredential).where(
                    UserCredential.user_id == user_id,
                    UserCredential.provider == provider,
                )
            )
        ).scalar_one_or_none()
        if not record:
            return False
        await db.delete(record)
        await db.commit()
        return True


async def save_mcp_token(user_id: UUID, token_hash: str, label: str = "default") -> None:
    """Per-user personal access token for external Knowledge MCP. We store the
    SHA-256 hash, never the plaintext."""
    async with AsyncSessionLocal() as db:
        await _upsert(
            db, user_id, "mcp_token",
            secret={"token_hash": token_hash},
            metadata={"label": label},
        )
        await db.commit()


async def find_user_by_mcp_token_hash(token_hash: str) -> UUID | None:
    """Look up a user_id by a hashed MCP token. O(n) over user_credentials —
    acceptable for the small user count this system targets."""
    async with AsyncSessionLocal() as db:
        records = (
            await db.execute(
                select(UserCredential).where(UserCredential.provider == "mcp_token")
            )
        ).scalars().all()
    for record in records:
        if not record.secret_payload:
            continue
        secret = decrypt(record.secret_payload)
        if isinstance(secret, dict) and secret.get("token_hash") == token_hash:
            return record.user_id
    return None
