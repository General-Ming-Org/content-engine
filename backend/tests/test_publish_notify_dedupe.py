"""Failure alerts: at most one email per post/article."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from services.publishing.failures import notify_publish_failure, publish_failure_title


@pytest.mark.asyncio
async def test_second_notify_for_same_post_is_skipped():
    user_id = uuid.uuid4()
    post_id = uuid.uuid4()

    with patch(
        "services.publishing.failures._claim_publish_failure_notify",
        new_callable=AsyncMock,
        side_effect=[True, False],
    ) as claim, patch(
        "services.publishing.failures._already_notified_in_db",
        new_callable=AsyncMock,
        return_value=False,
    ), patch(
        "services.notifications.notifier.create_user_error",
        new_callable=AsyncMock,
    ) as create_err:
        await notify_publish_failure(
            user_id,
            platform="linkedin",
            item_id=post_id,
            error="LinkedIn not authorized",
        )
        await notify_publish_failure(
            user_id,
            platform="linkedin",
            item_id=post_id,
            error="LinkedIn not authorized again",
        )

    assert claim.await_count == 2
    create_err.assert_awaited_once()
    args = create_err.await_args
    assert args[0][1] == publish_failure_title("linkedin", post_id)
