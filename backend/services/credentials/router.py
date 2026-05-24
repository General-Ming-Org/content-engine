"""User-facing endpoints for managing their own platform credentials.

Read endpoints return the **shape** of stored creds (presence + non-sensitive metadata),
never the encrypted secret. Write endpoints overwrite.
"""
import hashlib
import secrets

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from database import AsyncSessionLocal
from models.user import User
from models.user_credentials import UserCredential
from services.auth.deps import get_current_user
from config import get_settings
from services.credentials.store import (
    delete_credential,
    get_linkedin_app_credential,
    get_linkedin_credential,
    get_smtp_to_address,
    get_substack_credential,
    resolve_digest_recipient,
    resolve_linkedin_app_credentials,
    save_linkedin_app_credential,
    save_mcp_token,
    save_smtp_to,
    save_substack_credential,
)

_app_settings = get_settings()

logger = structlog.get_logger(__name__)
router = APIRouter()


class SubstackCreds(BaseModel):
    email: str
    password: str
    publication_url: str


class SmtpToBody(BaseModel):
    to_address: str


class LinkedInAppBody(BaseModel):
    client_id: str
    client_secret: str | None = None


class LinkedInRedirectModeBody(BaseModel):
    mode: str  # "app" | "api"


@router.get("")
async def list_credentials(user: User = Depends(get_current_user)) -> dict:
    """Return which providers are configured. Never returns the encrypted blob."""
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(select(UserCredential).where(UserCredential.user_id == user.id))
        ).scalars().all()
    return {
        r.provider: {
            "configured": True,
            "metadata": r.metadata_payload or {},
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    }


def _linkedin_app_payload(
    *,
    configured: bool,
    source: str | None,
    client_id: str | None,
    has_secret: bool,
    redirect_uri: str,
    redirect_mode: str,
    redirect_options: list[dict[str, str]],
) -> dict:
    return {
        "configured": configured,
        "source": source,
        "client_id": client_id,
        "has_secret": has_secret,
        "redirect_uri": redirect_uri,
        "redirect_mode": redirect_mode,
        "redirect_options": redirect_options,
    }


@router.get("/linkedin/app")
async def linkedin_app_status(user: User = Depends(get_current_user)) -> dict:
    """Developer App credentials (Client ID / Secret) — required before OAuth."""
    from services.publishing.linkedin_oauth import (
        get_redirect_mode,
        list_redirect_uri_options,
        resolve_linkedin_redirect_uri,
    )

    redirect_mode = await get_redirect_mode(user.id)
    redirect_uri = await resolve_linkedin_redirect_uri(user.id)
    redirect_options = list_redirect_uri_options()
    user_cred = await get_linkedin_app_credential(user.id)
    if user_cred:
        return _linkedin_app_payload(
            configured=True,
            source="user",
            client_id=user_cred["client_id"],
            has_secret=True,
            redirect_uri=redirect_uri,
            redirect_mode=redirect_mode,
            redirect_options=redirect_options,
        )

    if _app_settings.linkedin_client_id and _app_settings.linkedin_client_secret:
        return _linkedin_app_payload(
            configured=True,
            source="env",
            client_id=None,
            has_secret=True,
            redirect_uri=redirect_uri,
            redirect_mode=redirect_mode,
            redirect_options=redirect_options,
        )

    return _linkedin_app_payload(
        configured=False,
        source=None,
        client_id=None,
        has_secret=False,
        redirect_uri=redirect_uri,
        redirect_mode=redirect_mode,
        redirect_options=redirect_options,
    )


@router.put("/linkedin/app/redirect-mode")
async def set_linkedin_redirect_mode(
    body: LinkedInRedirectModeBody,
    user: User = Depends(get_current_user),
) -> dict:
    from services.publishing.linkedin_oauth import (
        RedirectMode,
        get_redirect_mode,
        list_redirect_uri_options,
        resolve_linkedin_redirect_uri,
        set_redirect_mode,
    )

    mode = (body.mode or "").strip().lower()
    if mode not in ("app", "api"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "mode must be 'app' (port 3000) or 'api' (port 8000)",
        )
    await set_redirect_mode(user.id, mode)  # type: ignore[arg-type]
    redirect_uri = await resolve_linkedin_redirect_uri(user.id)
    return {
        "redirect_mode": await get_redirect_mode(user.id),
        "redirect_uri": redirect_uri,
        "redirect_options": list_redirect_uri_options(),
    }


@router.put("/linkedin/app")
async def set_linkedin_app(
    body: LinkedInAppBody,
    user: User = Depends(get_current_user),
) -> dict:
    client_id = (body.client_id or "").strip()
    if not client_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Client ID is required")

    existing = await get_linkedin_app_credential(user.id)
    secret = (body.client_secret or "").strip()
    if not secret:
        if existing:
            secret = existing["client_secret"]
        else:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Client Secret is required")

    await save_linkedin_app_credential(user.id, client_id, secret)
    return {"configured": True, "client_id": client_id}


@router.delete("/linkedin/app", status_code=status.HTTP_204_NO_CONTENT)
async def delete_linkedin_app(user: User = Depends(get_current_user)) -> None:
    await delete_credential(user.id, "linkedin_app")


@router.get("/linkedin/status")
async def linkedin_status(user: User = Depends(get_current_user)) -> dict:
    app_configured = (await resolve_linkedin_app_credentials(user.id)) is not None
    cred = await get_linkedin_credential(user.id)
    account_connected = bool(cred and cred.get("access_token"))
    if not account_connected:
        return {
            "configured": False,
            "app_configured": app_configured,
        }
    return {
        "configured": True,
        "app_configured": app_configured,
        "person_urn": cred.get("person_urn"),
        "expires_at": cred.get("expires_at"),
    }


@router.delete("/linkedin", status_code=status.HTTP_204_NO_CONTENT)
async def delete_linkedin(user: User = Depends(get_current_user)) -> None:
    await delete_credential(user.id, "linkedin")


@router.get("/substack/status")
async def substack_status(user: User = Depends(get_current_user)) -> dict:
    cred = await get_substack_credential(user.id)
    if not cred:
        return {"configured": False}
    return {"configured": True, "publication_url": cred.get("publication_url")}


@router.put("/substack")
async def set_substack(
    body: SubstackCreds, user: User = Depends(get_current_user)
) -> dict:
    await save_substack_credential(user.id, body.email, body.password, body.publication_url)
    return {"configured": True}


@router.delete("/substack", status_code=status.HTTP_204_NO_CONTENT)
async def delete_substack(user: User = Depends(get_current_user)) -> None:
    await delete_credential(user.id, "substack")


@router.get("/smtp-to")
async def smtp_to_status(user: User = Depends(get_current_user)) -> dict:
    """Return where this user's digests and alert emails are sent."""
    override = await get_smtp_to_address(user.id)
    effective = await resolve_digest_recipient(user.id)
    return {
        "configured": bool(effective),
        "to_address": effective,
        "override": override,
        "account_email": user.email,
        "uses_account_email": bool(effective) and not override,
    }


@router.put("/smtp-to")
async def set_smtp_to(body: SmtpToBody, user: User = Depends(get_current_user)) -> dict:
    """Set the email address this user's digests + alerts go to. The operator's
    SMTP credentials in env are used to send."""
    await save_smtp_to(user.id, body.to_address)
    return {"to_address": body.to_address}


@router.post("/mcp-token")
async def issue_mcp_token(user: User = Depends(get_current_user)) -> dict:
    """Issue a fresh personal MCP token. Returned ONCE — store it; we keep only the hash."""
    plaintext = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
    await save_mcp_token(user.id, token_hash)
    logger.info("mcp_token_issued", user_id=str(user.id))
    return {
        "token": plaintext,
        "warning": "This is the only time you'll see this token. Store it securely.",
    }


@router.delete("/mcp-token", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_mcp_token(user: User = Depends(get_current_user)) -> None:
    await delete_credential(user.id, "mcp_token")
