"""LinkedIn OAuth helpers (Authlib + signed state)."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.publishing.linkedin_oauth import (
    decode_oauth_state,
    get_linkedin_redirect_uri,
    sign_oauth_state,
)


def test_oauth_state_roundtrip():
    uid = uuid.uuid4()
    state = sign_oauth_state(uid)
    assert decode_oauth_state(state) == uid


def test_oauth_state_rejects_tampering():
    with pytest.raises(ValueError):
        decode_oauth_state("not-a-valid-state")


def test_redirect_uri_uses_app_public_url():
    with patch("services.publishing.linkedin_oauth.settings") as mock_settings:
        mock_settings.linkedin_redirect_uri = ""
        mock_settings.app_public_url = "http://localhost:3000"
        mock_settings.api_public_url = "http://localhost:8000"
        assert get_linkedin_redirect_uri() == (
            "http://localhost:3000/api/publish/linkedin/callback"
        )


@pytest.mark.asyncio
async def test_create_authorization_url_uses_authlib():
    uid = uuid.uuid4()
    # Authlib's create_authorization_url is sync; aclose is async.
    mock_client = MagicMock()
    mock_client.create_authorization_url = MagicMock(return_value=(
        "https://www.linkedin.com/oauth/v2/authorization?test=1",
        "state",
    ))
    mock_client.aclose = AsyncMock()

    with (
        patch(
            "services.publishing.linkedin_oauth.create_oauth_client",
            AsyncMock(return_value=mock_client),
        ),
        patch(
            "services.publishing.linkedin_oauth.resolve_linkedin_redirect_uri",
            AsyncMock(return_value="http://localhost:3000/api/publish/linkedin/callback"),
        ),
    ):
        from services.publishing.linkedin_oauth import create_authorization_url

        url, redirect = await create_authorization_url(uid)
        assert "linkedin.com" in url
        assert redirect.endswith("/api/publish/linkedin/callback")
        mock_client.create_authorization_url.assert_called_once()
        mock_client.aclose.assert_awaited_once()
