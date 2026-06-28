"""Publishing routes.

OAuth callback intentionally has NO auth dependency — LinkedIn redirects unauthenticated
browsers here. The `state` param carries a signed user_id from when we generated
the OAuth URL, so we know which user is completing the flow.
"""
import uuid
from typing import Any
from urllib.parse import quote

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.content import Article, Post
from models.user import User
from config import get_settings
from services.auth.deps import get_current_user

router = APIRouter()
# Public — LinkedIn redirects the user's browser here without a JWT.
oauth_router = APIRouter()
settings = get_settings()
logger = structlog.get_logger(__name__)


def _settings_redirect(query: str) -> str:
    base = (settings.app_public_url or "http://localhost:3000").rstrip("/")
    return f"{base}/settings?{query}"


@router.get("/linkedin/oauth-url")
async def linkedin_oauth_url(
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Issue a LinkedIn OAuth URL bound to the calling user. The `state` parameter
    carries a signed user_id so the callback can attribute the tokens correctly."""
    from services.credentials.store import resolve_linkedin_app_credentials
    from services.publishing.linkedin_oauth import (
        LINKEDIN_OAUTH_SCOPES,
        create_authorization_url,
    )

    if not await resolve_linkedin_app_credentials(user.id):
        raise HTTPException(
            status_code=400,
            detail="LinkedIn Developer App not configured. Add Client ID and Client Secret in Settings.",
        )

    url, redirect_uri = await create_authorization_url(user.id)
    return {
        "url": url,
        "redirect_uri": redirect_uri,
        "scopes": LINKEDIN_OAUTH_SCOPES,
    }


@oauth_router.get("/linkedin/callback", name="linkedin_oauth_callback")
async def linkedin_oauth_callback(
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    error_description: str | None = Query(None),
):
    """Exchange code, persist tokens, redirect user back to Settings in the web app."""
    from services.publishing.linkedin_api import complete_oauth
    from services.publishing.linkedin_oauth import decode_oauth_state, resolve_linkedin_redirect_uri

    redirect_uri = ""
    if state:
        try:
            redirect_uri = await resolve_linkedin_redirect_uri(decode_oauth_state(state))
        except ValueError:
            pass

    if error:
        reason = (error_description or error or "access_denied")[:240]
        logger.warning(
            "linkedin_oauth_denied",
            error=error,
            error_description=error_description,
            redirect_uri=redirect_uri,
        )
        return RedirectResponse(
            _settings_redirect(f"linkedin=denied&reason={quote(reason)}")
        )

    if not code or not state:
        logger.warning("linkedin_oauth_callback_missing_params", has_code=bool(code), has_state=bool(state))
        hint = quote(
            f"Missing authorization code. Register this exact redirect URL in LinkedIn: {redirect_uri}"
        )
        return RedirectResponse(_settings_redirect(f"linkedin=error&reason={hint}"))

    try:
        user_id = decode_oauth_state(state)
    except ValueError:
        logger.warning("linkedin_oauth_invalid_state")
        return RedirectResponse(
            _settings_redirect("linkedin=error&reason=" + quote("Invalid OAuth state — try Connect again."))
        )

    redirect_uri = await resolve_linkedin_redirect_uri(user_id)

    try:
        await complete_oauth(user_id, code, redirect_uri)
    except Exception as exc:
        logger.exception("linkedin_oauth_complete_failed", error=str(exc))
        return RedirectResponse(
            _settings_redirect("linkedin=error&reason=" + quote(str(exc)[:240]))
        )

    return RedirectResponse(_settings_redirect("linkedin=connected"))


@router.post("/linkedin/{post_id}")
async def publish_linkedin_now(
    post_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Publish a post now (skip the 1-hour queue). Must own the post."""
    post = (await db.execute(
        select(Post).where(Post.id == post_id, Post.user_id == user.id)
    )).scalar_one_or_none()
    if not post:
        raise HTTPException(404, "Post not found")
    from services.scheduler.tasks import publish_linkedin_post
    task = publish_linkedin_post.delay(str(post_id))
    return {"status": "triggered", "task_id": task.id}


@router.post("/substack/{article_id}")
async def publish_substack_now(
    article_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    article = (await db.execute(
        select(Article).where(Article.id == article_id, Article.user_id == user.id)
    )).scalar_one_or_none()
    if not article:
        raise HTTPException(404, "Article not found")
    from services.scheduler.tasks import publish_substack_article
    task = publish_substack_article.delay(str(article_id))
    return {"status": "triggered", "task_id": task.id}
