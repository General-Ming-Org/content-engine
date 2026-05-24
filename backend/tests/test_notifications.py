"""Notification service unit tests."""
import pytest


@pytest.mark.asyncio
async def test_create_error_notification(db_session):
    from unittest.mock import patch
    with patch("services.notifications.alerts.send_alert_email") as mock_email:
        mock_email.return_value = None
        from services.notifications.notifier import create_error_notification
        await create_error_notification("LinkedIn publish failed", "HTTP 403 Forbidden")

    from sqlalchemy import select
    from models.notifications import Notification
    result = await db_session.execute(
        select(Notification).where(Notification.title == "LinkedIn publish failed")
    )
    notif = result.scalar_one_or_none()
    assert notif is not None
    assert notif.type == "error"
    assert notif.is_read is False


@pytest.mark.asyncio
async def test_create_system_notification(db_session):
    from services.notifications.notifier import create_system_notification
    await create_system_notification("Daily Summary — Jan 01", "2 posts published, 847 impressions")

    from sqlalchemy import select
    from models.notifications import Notification
    result = await db_session.execute(
        select(Notification).where(Notification.type == "system")
    )
    notif = result.scalar_one_or_none()
    assert notif is not None
    assert notif.emailed is False  # System notifications don't send email
