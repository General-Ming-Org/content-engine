"""Queue processor must not leave items in ``queued`` after permanent publish failures."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from models.content import Post


@pytest.mark.asyncio
async def test_queue_marks_failed_when_linkedin_not_authorized(db_session, test_user):
    post = Post(
        id=uuid.uuid4(),
        user_id=test_user.id,
        content="Test queued post",
        hashtags=[],
        voice_style="analytical",
        status="queued",
        queued_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    db_session.add(post)
    await db_session.commit()

    with patch(
        "services.publishing.queue_manager.publish_post",
        new_callable=AsyncMock,
        side_effect=RuntimeError("LinkedIn not authorized for user"),
    ), patch(
        "services.publishing.queue_manager.publish_article",
        new_callable=AsyncMock,
        return_value={"status": "already_published"},
    ), patch(
        "services.publishing.failures.notify_publish_failure",
        new_callable=AsyncMock,
    ):
        from services.publishing.queue_manager import process_queue

        result = await process_queue()

    assert len(result["errors"]) == 1

    await db_session.refresh(post)
    assert post.status == "failed"
    assert post.queued_at is None
