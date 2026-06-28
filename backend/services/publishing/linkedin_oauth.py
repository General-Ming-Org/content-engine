"""LinkedIn OAuth 2.0 via Authlib (authorization URL, token exchange, userinfo).

Per-user Client ID / Secret from ``user_credentials`` (Settings → LinkedIn).
Publishing and API calls remain in ``linkedin_api.py``.
"""
from __future__ import annotations

import uuid
from typing import Any, Literal

import structlog
from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.integrations.base_client.errors import OAuthError
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import select

from config import get_settings
from database import AsyncSessionLocal
from models.settings import UserSetting
from services.credentials.store import get_linkedin_app_credential, resolve_linkedin_app_credentials

logger = structlog.get_logger(__name__)
settings = get_settings()

LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
LINKEDIN_CALLBACK_PATH = "/api/publish/linkedin/callback"
LINKEDIN_REDIRECT_MODE_KEY = "linkedin_oauth_redirect_mode"

RedirectMode = Literal["app", "api"]

# OpenID + Share on LinkedIn — do not add org / deprecated scopes without product approval.
LINKEDIN_OAUTH_SCOPES = "openid profile email w_member_social"


def _callback_base_for_mode(mode: RedirectMode) -> str:
    if (settings.linkedin_redirect_uri or "").strip():
        return (settings.linkedin_redirect_uri or "").strip().rstrip("/").removesuffix(
            LINKEDIN_CALLBACK_PATH
        )
    if mode == "api":
        return (settings.api_public_url or "http://localhost:8000").rstrip("/")
    return (settings.app_public_url or "http://localhost:3000").rstrip("/")


def list_redirect_uri_options() -> list[dict[str, str]]:
    """Both common local dev callbacks — user must register the one they select."""
    return [
        {
            "mode": "app",
            "label": "Web app (port 3000) — recommended when using http://localhost:3000",
            "uri": f"{_callback_base_for_mode('app')}{LINKEDIN_CALLBACK_PATH}",
        },
        {
            "mode": "api",
            "label": "API directly (port 8000) — if you registered localhost:8000 in LinkedIn",
            "uri": f"{_callback_base_for_mode('api')}{LINKEDIN_CALLBACK_PATH}",
        },
    ]


async def get_redirect_mode(user_id: uuid.UUID) -> RedirectMode:
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(UserSetting).where(
                    UserSetting.user_id == user_id,
                    UserSetting.key == LINKEDIN_REDIRECT_MODE_KEY,
                )
            )
        ).scalar_one_or_none()
    if row and isinstance(row.value, dict):
        mode = row.value.get("mode")
        if mode in ("app", "api"):
            return mode
    return "app"


async def set_redirect_mode(user_id: uuid.UUID, mode: RedirectMode) -> None:
    if mode not in ("app", "api"):
        raise ValueError("mode must be 'app' or 'api'")
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(UserSetting).where(
                    UserSetting.user_id == user_id,
                    UserSetting.key == LINKEDIN_REDIRECT_MODE_KEY,
                )
            )
        ).scalar_one_or_none()
        if row:
            row.value = {"mode": mode}
        else:
            db.add(
                UserSetting(
                    user_id=user_id,
                    key=LINKEDIN_REDIRECT_MODE_KEY,
                    value={"mode": mode},
                )
            )
        await db.commit()


def get_linkedin_redirect_uri(mode: RedirectMode = "app") -> str:
    """Sync helper for display/tests. OAuth flow uses ``resolve_linkedin_redirect_uri``."""
    explicit = (settings.linkedin_redirect_uri or "").strip()
    if explicit:
        return explicit.rstrip("/")
    return f"{_callback_base_for_mode(mode)}{LINKEDIN_CALLBACK_PATH}"


async def resolve_linkedin_redirect_uri(user_id: uuid.UUID) -> str:
    """Async resolver — use everywhere in OAuth flow."""
    explicit = (settings.linkedin_redirect_uri or "").strip()
    if explicit:
        return explicit.rstrip("/")
    mode = await get_redirect_mode(user_id)
    return f"{_callback_base_for_mode(mode)}{LINKEDIN_CALLBACK_PATH}"


def _state_serializer() -> URLSafeSerializer:
    return URLSafeSerializer(settings.app_secret_key, salt="linkedin-oauth")


def sign_oauth_state(user_id: uuid.UUID) -> str:
    return _state_serializer().dumps(str(user_id))


def decode_oauth_state(state: str) -> uuid.UUID:
    try:
        return uuid.UUID(_state_serializer().loads(state))
    except (BadSignature, ValueError) as exc:
        raise ValueError("Invalid OAuth state") from exc


async def require_linkedin_app_credentials(user_id: uuid.UUID) -> tuple[str, str]:
    pair = await resolve_linkedin_app_credentials(user_id)
    if not pair:
        raise RuntimeError(
            "LinkedIn Developer App not configured. Add Client ID and Client Secret in Settings."
        )
    return pair


async def create_oauth_client(user_id: uuid.UUID) -> AsyncOAuth2Client:
    client_id, client_secret = await require_linkedin_app_credentials(user_id)
    redirect_uri = await resolve_linkedin_redirect_uri(user_id)
    # LinkedIn's token endpoint requires the client_secret in the POST body,
    # not in the HTTP Basic header (Authlib's default). Without this override
    # LinkedIn returns `invalid_request: A required parameter "client_secret" is missing`.
    return AsyncOAuth2Client(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=LINKEDIN_OAUTH_SCOPES,
        token_endpoint_auth_method="client_secret_post",
    )


async def create_authorization_url(user_id: uuid.UUID) -> tuple[str, str, str]:
    """Return (authorize_url, redirect_uri, client_id) for the member OAuth consent screen."""
    redirect_uri = await resolve_linkedin_redirect_uri(user_id)
    client_id, _ = await require_linkedin_app_credentials(user_id)
    client = await create_oauth_client(user_id)
    try:
        state = sign_oauth_state(user_id)
        uri, _ = client.create_authorization_url(
            LINKEDIN_AUTH_URL,
            state=state,
            redirect_uri=redirect_uri,
        )
        logger.info(
            "linkedin_oauth_url_created",
            user_id=str(user_id),
            client_id=client_id,
            redirect_uri=redirect_uri,
        )
        return uri, redirect_uri, client_id
    finally:
        await client.aclose()


async def exchange_authorization_code(user_id: uuid.UUID, code: str) -> dict[str, Any]:
    """Authorization code → token response (access_token, expires_in, …)."""
    redirect_uri = await resolve_linkedin_redirect_uri(user_id)
    client = await create_oauth_client(user_id)
    try:
        return await client.fetch_token(
            LINKEDIN_TOKEN_URL,
            code=code,
            grant_type="authorization_code",
        )
    except OAuthError as exc:
        logger.error(
            "linkedin_token_exchange_failed",
            error=str(exc),
            redirect_uri=redirect_uri,
        )
        raise RuntimeError(
            f"LinkedIn token exchange failed: {exc.error}. "
            f"Register this exact redirect URL in your Developer App: {redirect_uri}"
        ) from exc
    finally:
        await client.aclose()


async def fetch_linkedin_userinfo(access_token: str) -> dict[str, Any]:
    """OpenID userinfo for person URN (``sub``)."""
    client = AsyncOAuth2Client(token={"access_token": access_token, "token_type": "Bearer"})
    try:
        resp = await client.get(LINKEDIN_USERINFO_URL)
        resp.raise_for_status()
        return resp.json()
    finally:
        await client.aclose()
