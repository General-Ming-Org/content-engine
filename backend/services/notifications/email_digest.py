"""Per-user morning preview and evening recap email digests.

The operator runs one SMTP outbound (env config). Each user provides their
own recipient address via credentials/user_credentials (provider='smtp').
Digest tasks iterate over active users and send each their own scoped digest.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import aiosmtplib
import structlog
from sqlalchemy import select

from config import get_settings
from database import AsyncSessionLocal
from models.content import Post
from models.engagement import EngagementAction
from models.user import User
from services.credentials.store import resolve_digest_recipient
from services.notifications.email_branding import build_branded_message, digest_html_from_plain

logger = structlog.get_logger(__name__)
settings = get_settings()


async def send_email(
    to_address: str,
    subject: str,
    body: str,
    *,
    email_title: str | None = None,
    email_subtitle: str | None = None,
) -> None:
    """Send a branded HTML + plain-text email via the operator's SMTP."""
    if not all([settings.smtp_host, settings.smtp_username, settings.smtp_password]):
        logger.warning("smtp_not_configured_email_skipped", subject=subject)
        return

    title, html_inner = digest_html_from_plain(body)
    msg = build_branded_message(
        to_address=to_address,
        subject=subject,
        plain_body=body,
        html_inner=html_inner,
        title=email_title or title,
        subtitle=email_subtitle,
    )

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            start_tls=True,
        )
        logger.info("email_sent", subject=subject, to=to_address)
    except Exception as exc:
        logger.error("email_send_failed", subject=subject, error=str(exc))
        raise


async def _build_morning_for(user_id: UUID) -> str:
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
    today_end = today_start + timedelta(days=1)
    week_end = today_start + timedelta(days=7)

    async with AsyncSessionLocal() as db:
        queued_today = (await db.execute(
            select(Post).where(
                Post.user_id == user_id,
                Post.status.in_(["queued", "scheduled"]),
                Post.scheduled_at >= today_start,
                Post.scheduled_at < today_end,
            )
        )).scalars().all()

        queue_window = (await db.execute(
            select(Post).where(Post.user_id == user_id, Post.status == "queued")
        )).scalars().all()

        upcoming = (await db.execute(
            select(Post).where(
                Post.user_id == user_id,
                Post.status == "scheduled",
                Post.scheduled_at >= today_start,
                Post.scheduled_at < week_end,
            )
        )).scalars().all()

    lines = [f"Morning Preview — {today.strftime('%A, %B %d')}", "=" * 60, ""]
    if queue_window:
        lines.append(f"IN 1-HOUR QUEUE ({len(queue_window)} items):")
        for p in queue_window:
            lines.append(f"  - LinkedIn: {p.content[:60]}...")
        lines.append("")
    if queued_today:
        lines.append(f"SCHEDULED TODAY ({len(queued_today)} items):")
        for p in queued_today:
            t = p.scheduled_at.strftime("%H:%M UTC") if p.scheduled_at else "TBD"
            lines.append(f"  - LinkedIn @ {t}: {p.content[:60]}...")
        lines.append("")
    if upcoming:
        lines.append(f"UPCOMING THIS WEEK ({len(upcoming)} items):")
        for p in upcoming:
            day = p.scheduled_at.strftime("%A") if p.scheduled_at else "TBD"
            lines.append(f"  - {day}: {p.content[:60]}...")
        lines.append("")
    if not queue_window and not queued_today and not upcoming:
        lines.append("Nothing scheduled today.")
    return "\n".join(lines)


async def _build_evening_for(user_id: UUID) -> str:
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
    today_end = today_start + timedelta(days=1)

    async with AsyncSessionLocal() as db:
        published = (await db.execute(
            select(Post).where(
                Post.user_id == user_id,
                Post.status == "published",
                Post.published_at >= today_start,
                Post.published_at < today_end,
            )
        )).scalars().all()

        failed = (await db.execute(
            select(Post).where(
                Post.user_id == user_id,
                Post.status == "failed",
                Post.updated_at >= today_start,
            )
        )).scalars().all()

        engagements = (await db.execute(
            select(EngagementAction).where(
                EngagementAction.user_id == user_id,
                EngagementAction.created_at >= today_start,
                EngagementAction.status == "posted",
            )
        )).scalars().all()

    lines = [f"Evening Recap — {today.strftime('%A, %B %d')}", "=" * 60, ""]
    if published:
        lines.append(f"PUBLISHED TODAY ({len(published)} posts):")
        for p in published:
            metrics = p.metrics or {}
            imp = metrics.get("impressions", "—")
            eng = metrics.get("engagement_rate", "—")
            lines.append(f"  - {p.content[:70]}...")
            lines.append(f"    Impressions: {imp}  |  Engagement: {eng}")
        lines.append("")
    else:
        lines.append("Nothing published today.\n")
    if engagements:
        lines.append(f"ENGAGEMENT ({len(engagements)} replies sent today)\n")
    if failed:
        lines.append(f"FAILURES ({len(failed)} posts failed — check dashboard):")
        for p in failed:
            lines.append(f"  - {p.id}: {p.content[:60]}...")
        lines.append("")
    return "\n".join(lines)


async def send_morning_digest() -> dict[str, Any]:
    """Iterate active users, send each their own morning digest."""
    async with AsyncSessionLocal() as db:
        users = (await db.execute(select(User).where(User.is_active.is_(True)))).scalars().all()

    sent = 0
    for u in users:
        to = await resolve_digest_recipient(u.id)
        if not to:
            logger.debug("digest_recipient_missing", user_id=str(u.id))
            continue
        body = await _build_morning_for(u.id)
        try:
            await send_email(to, f"[Content Engine] Morning Preview — {date.today().strftime('%b %d')}", body)
            sent += 1
        except Exception as exc:
            logger.error("morning_email_user_failed", user_id=str(u.id), error=str(exc))
    return {"status": "sent", "users": sent, "date": str(date.today())}


async def send_evening_digest() -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        users = (await db.execute(select(User).where(User.is_active.is_(True)))).scalars().all()

    sent = 0
    for u in users:
        to = await resolve_digest_recipient(u.id)
        if not to:
            logger.debug("digest_recipient_missing", user_id=str(u.id))
            continue
        body = await _build_evening_for(u.id)
        try:
            await send_email(to, f"[Content Engine] Evening Recap — {date.today().strftime('%b %d')}", body)
            sent += 1
        except Exception as exc:
            logger.error("evening_email_user_failed", user_id=str(u.id), error=str(exc))
    return {"status": "sent", "users": sent, "date": str(date.today())}
