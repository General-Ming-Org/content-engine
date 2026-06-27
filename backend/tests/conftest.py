"""Shared pytest fixtures for all tests. All external APIs are mocked — no real calls."""
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from models.user import User

# In-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSessionLocal = async_sessionmaker(
    _test_engine, class_=AsyncSession, expire_on_commit=False
)


class _SessionContext:
    """Route production AsyncSessionLocal() calls to the test session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if exc is not None:
            await self._session.rollback()


@pytest_asyncio.fixture
async def setup_db():
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(delete(table))


@pytest_asyncio.fixture
async def db_session(setup_db) -> AsyncGenerator[AsyncSession, None]:
    async with _TestSessionLocal() as session:
        def _session_factory() -> _SessionContext:
            return _SessionContext(session)

        with patch("database.AsyncSessionLocal", side_effect=_session_factory):
            yield session


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"test-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="test-password-hash",
        name="Test User",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(app=app, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def mock_llm_generate():
    """Mock LiteLLM entrypoint used by all content/research agents."""
    with patch("services.ai.llm_client.generate", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture
def mock_anthropic():
    """Mock Anthropic API client — returns deterministic responses."""
    with patch("anthropic.AsyncAnthropic") as mock_class:
        mock_instance = AsyncMock()
        mock_class.return_value = mock_instance
        mock_instance.messages.create = AsyncMock(return_value=MagicMock(
            content=[MagicMock(text='{"summary": "Test summary", "key_facts": ["fact 1", "fact 2"], "why_it_matters": "It matters.", "trade_offs": "Some trade-off.", "suggested_voice": "analytical", "confidence": 8}')]
        ))
        yield mock_instance


@pytest.fixture
def mock_tavily():
    """Mock Tavily search results."""
    with patch("services.research.searcher.search_tavily") as mock:
        mock.return_value = [
            {
                "title": "Test Article: eBPF in Production",
                "url": "https://example.com/test",
                "content": "eBPF allows kernel-level observability without kernel modifications...",
                "domain": "sre_infra",
            }
        ]
        yield mock


@pytest.fixture
def mock_linkedin_publish():
    with patch("services.publishing.linkedin_api.publish_post") as mock:
        mock.return_value = {"status": "published", "linkedin_post_id": "test-li-id-123"}
        yield mock


@pytest.fixture
def mock_substack_publish():
    with patch("services.publishing.substack_auto.publish_article") as mock:
        mock.return_value = {"status": "published", "substack_url": "https://test.substack.com/p/test"}
        yield mock
