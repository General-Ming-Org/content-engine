"""Immediate per-user error alert emails."""
from uuid import UUID

import structlog

from config import get_settings
from services.credentials.store import resolve_digest_recipient
from services.notifications.email_digest import send_email

logger = structlog.get_logger(__name__)
settings = get_settings()


async def send_alert_email(user_id: UUID, title: str, message: str) -> None:
    """Send an alert to the user's digest recipient (override or account email)."""
    to_address = await resolve_digest_recipient(user_id)
    if not to_address:
        logger.debug("digest_recipient_missing", user_id=str(user_id), title=title)
        return
    if not settings.smtp_username:
        logger.warning("smtp_not_configured_alert_skipped", title=title)
        return

    subject = f"[Content Engine Alert] {title}"
    body = f"""
Content Engine Error Alert
==========================

{title}

{message}

This is an automated alert. Log in to your dashboard to view details and take action.
"""
    await send_email(
        to_address=to_address,
        subject=subject,
        body=body.strip(),
        email_title=title,
        email_subtitle="An error occurred in your Content Engine workspace.",
    )
