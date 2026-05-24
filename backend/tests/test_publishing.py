"""Publishing service unit tests."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from services.publishing.queue_manager import QUEUE_DELAY_MINUTES


@pytest.mark.asyncio
async def test_queue_delay_constant():
    assert QUEUE_DELAY_MINUTES == 60


@pytest.mark.asyncio
async def test_idempotency_already_published():
    """publish_post should not call the API if linkedin_post_id is already set."""
    from unittest.mock import MagicMock, patch
    mock_post = MagicMock()
    mock_post.id = uuid.uuid4()
    mock_post.linkedin_post_id = "existing-id-123"
    mock_post.content = "Test post"

    with patch("services.publishing.linkedin_api.AsyncSessionLocal") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_post)
        ))
        mock_session_cls.return_value = mock_session

        from services.publishing.linkedin_api import publish_post
        result = await publish_post(str(mock_post.id))
        assert result["status"] == "already_published"
        assert result["linkedin_post_id"] == "existing-id-123"


@pytest.mark.asyncio
async def test_safety_filter_blocks_political():
    from services.engagement.safety import should_skip_comment
    skip, reason = should_skip_comment("This is about the Democrat party platform")
    assert skip is True
    assert "political" in reason


@pytest.mark.asyncio
async def test_safety_filter_blocks_spam():
    from services.engagement.safety import should_skip_comment
    skip, reason = should_skip_comment("Check out my crypto project at https://example.com/scam")
    assert skip is True


@pytest.mark.asyncio
async def test_safety_filter_allows_good_comment():
    from services.engagement.safety import should_skip_comment
    skip, _ = should_skip_comment(
        "I've been dealing with this exact cardinality explosion problem. "
        "We ended up using probabilistic sampling at the ingestion layer."
    )
    assert skip is False


def test_reply_validation_rejects_anti_pattern():
    from services.engagement.safety import validate_reply
    valid, reason = validate_reply("Great point! I totally agree with your perspective here.")
    assert valid is False
    assert "anti_pattern" in reason


def test_reply_validation_accepts_good_reply():
    from services.engagement.safety import validate_reply
    reply = (
        "The probabilistic approach works well at lower cardinalities but breaks down "
        "when you have high-variance service meshes. We found tail-based sampling with "
        "a configurable floor (we use 2% in prod) handles the edge cases better."
    )
    valid, _ = validate_reply(reply)
    assert valid is True
