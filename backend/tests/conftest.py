"""
Pytest configuration and shared fixtures.

Provides:
- Database fixtures (in-memory SQLite with rollback isolation)
- FastAPI app with dependency overrides
- Async HTTP client for endpoint testing
- Authentication fixtures (users, tokens)
- Mock utilities for external services
"""
import os
import pytest
import pytest_asyncio
from typing import AsyncGenerator
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

# Set test environment BEFORE any app imports
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars"
os.environ["DATABASE_URL"] = "sqlite:///./test_db.db"  # Simple file-based for app compatibility
os.environ["DEBUG"] = "false"
os.environ["LOG_DIR"] = "./test_logs"  # Use local directory for test logs

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession
)
from sqlalchemy.pool import StaticPool

from app.main import app as fastapi_app
from app.models.database import Base
from app.models.user import User, UserRole, UserStatus
from app.dependencies import get_async_db
from app.api.v1.auth import create_access_token


# =============================================================================
# DATABASE FIXTURES
# =============================================================================

@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """
    Create in-memory SQLite engine for each test function.
    Tables are created fresh for each test.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # Single connection for in-memory DB
        echo=False
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_db(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Async database session with automatic rollback.
    Each test gets isolated data that is rolled back after completion.
    """
    async_session = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False
    )

    async with async_session() as session:
        yield session
        # Rollback any changes for test isolation
        await session.rollback()


# =============================================================================
# APPLICATION FIXTURES
# =============================================================================

@pytest_asyncio.fixture
async def app(test_db: AsyncSession) -> AsyncGenerator[FastAPI, None]:
    """
    FastAPI application with test dependency overrides.
    Replaces real database with test database.
    """
    async def override_get_async_db():
        yield test_db

    fastapi_app.dependency_overrides[get_async_db] = override_get_async_db

    yield fastapi_app

    # Cleanup overrides after test
    fastapi_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    Async HTTP client for testing endpoints.
    Uses httpx.AsyncClient with ASGITransport for in-process testing.
    """
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True
    ) as ac:
        yield ac


# =============================================================================
# USER FIXTURES
# =============================================================================

@pytest_asyncio.fixture
async def test_user(test_db: AsyncSession) -> User:
    """Create a regular test user with ACTIVE status."""
    from argon2 import PasswordHasher
    ph = PasswordHasher()

    user = User(
        username="testuser",
        email="testuser@example.com",
        hashed_password=ph.hash("testpassword123"),
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
        is_active=True,
        created_at=datetime.utcnow()
    )
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_user(test_db: AsyncSession) -> User:
    """Create an admin test user."""
    from argon2 import PasswordHasher
    ph = PasswordHasher()

    user = User(
        username="admin",
        email="admin@example.com",
        hashed_password=ph.hash("adminpassword123"),
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        is_active=True,
        created_at=datetime.utcnow()
    )
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    return user


@pytest_asyncio.fixture
async def pending_user(test_db: AsyncSession) -> User:
    """Create a pending (unapproved) user."""
    from argon2 import PasswordHasher
    ph = PasswordHasher()

    user = User(
        username="pendinguser",
        email="pending@example.com",
        hashed_password=ph.hash("pendingpassword123"),
        role=UserRole.USER,
        status=UserStatus.PENDING,
        is_active=True,
        created_at=datetime.utcnow()
    )
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    return user


# =============================================================================
# AUTHENTICATION FIXTURES
# =============================================================================

@pytest.fixture
def user_token(test_user: User) -> str:
    """JWT token for regular user."""
    return create_access_token(
        data={
            "user_id": test_user.id,
            "username": test_user.username,
            "role": test_user.role.value
        }
    )


@pytest.fixture
def admin_token(admin_user: User) -> str:
    """JWT token for admin user."""
    return create_access_token(
        data={
            "user_id": admin_user.id,
            "username": admin_user.username,
            "role": admin_user.role.value
        }
    )


def auth_headers(token: str) -> dict:
    """Helper to create Authorization header."""
    return {"Authorization": f"Bearer {token}"}


# =============================================================================
# MOCK FIXTURES FOR EXTERNAL SERVICES
# =============================================================================

@pytest.fixture
def mock_httpx_response():
    """Factory for creating mock httpx responses."""
    def _create(status_code=200, json_data=None, text=""):
        response = MagicMock()
        response.status_code = status_code
        response.text = text
        response.json.return_value = json_data or {}
        response.raise_for_status = MagicMock()
        if status_code >= 400:
            from httpx import HTTPStatusError
            response.raise_for_status.side_effect = HTTPStatusError(
                message=f"HTTP {status_code}",
                request=MagicMock(),
                response=response
            )
        return response
    return _create


@pytest.fixture
def mock_httpx_client():
    """
    Factory for creating mock httpx.AsyncClient.
    Prevents all real HTTP calls.
    """
    def _create(responses: dict = None):
        """
        Create mock client with predefined responses.

        Args:
            responses: Dict mapping URL patterns to response data
                       {"tmdb.org": {"status_code": 200, "json": {...}}}
        """
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        async def mock_request(method, url, **kwargs):
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {}
            response.text = ""
            response.raise_for_status = MagicMock()

            if responses:
                for pattern, resp_data in responses.items():
                    if pattern in str(url):
                        response.status_code = resp_data.get("status_code", 200)
                        response.json.return_value = resp_data.get("json", {})
                        response.text = resp_data.get("text", "")
                        if resp_data.get("status_code", 200) >= 400:
                            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                                message=f"HTTP {resp_data['status_code']}",
                                request=MagicMock(),
                                response=response
                            )
                        break

            return response

        mock_client.get = AsyncMock(side_effect=lambda url, **kw: mock_request("GET", url, **kw))
        mock_client.post = AsyncMock(side_effect=lambda url, **kw: mock_request("POST", url, **kw))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        return mock_client

    return _create


# =============================================================================
# AI PROVIDER FIXTURES (preserved from original)
# =============================================================================

@pytest.fixture
def mock_ai_models_response():
    """Mock response for /v1/models endpoint."""
    return {
        "data": [
            {"id": "qwen3-vl-30b", "owned_by": "local", "created": 1234567890},
            {"id": "llama-3-8b", "owned_by": "local", "created": 1234567891},
        ]
    }


@pytest.fixture
def mock_chat_response():
    """Mock response for /v1/chat/completions endpoint."""
    return {
        "choices": [
            {
                "message": {
                    "content": '{"rankings": [{"index": 1, "score": 95, "reason": "Best quality"}]}'
                }
            }
        ],
        "model": "qwen3-vl-30b",
        "usage": {"prompt_tokens": 100, "completion_tokens": 50}
    }


@pytest.fixture
def mock_chat_response_with_thinking():
    """Mock response with Qwen3 thinking tags."""
    return {
        "choices": [
            {
                "message": {
                    "content": '<think>Let me analyze this...</think>{"rankings": [{"index": 1, "score": 95}]}'
                }
            }
        ],
        "model": "qwen3-vl-30b"
    }


@pytest.fixture
def ai_config():
    """Create a test AI configuration."""
    from app.services.ai_provider.config import AIConfig, ProviderType
    return AIConfig(
        provider_type=ProviderType.LLAMA_CPP,
        base_url="http://localhost:8080",
        api_key=None,
        model_scoring="qwen3-vl-30b",
        model_rename="qwen3-vl-30b",
        model_analysis="qwen3-vl-30b",
        timeout=30.0,
        is_enabled=True
    )


@pytest.fixture
def ai_config_openai():
    """Create a test OpenAI configuration."""
    from app.services.ai_provider.config import AIConfig, ProviderType
    return AIConfig(
        provider_type=ProviderType.OPENAI,
        base_url="https://api.openai.com",
        api_key="sk-test-key",
        model_scoring="gpt-4",
        timeout=60.0,
        is_enabled=True
    )


@pytest.fixture
def ai_config_openrouter():
    """Create a test OpenRouter configuration."""
    from app.services.ai_provider.config import AIConfig, ProviderType
    return AIConfig(
        provider_type=ProviderType.OPENROUTER,
        base_url="https://openrouter.ai",
        api_key="sk-or-test-key",
        model_scoring="openai/gpt-4",
        timeout=60.0,
        is_enabled=True
    )


# =============================================================================
# DOMAIN FIXTURES (preserved from original)
# =============================================================================

@pytest.fixture
def mock_torrent_result():
    """Create a mock torrent result."""
    torrent = MagicMock()
    torrent.name = "Movie.2024.1080p.HEVC.x265.MULTI"
    torrent.size_human = "4.5 GB"
    torrent.seeders = 50
    torrent.quality = "1080p"
    torrent.release_group = "SPARKS"
    torrent.has_french_audio = True
    torrent.ai_score = None
    torrent.ai_reasoning = None
    return torrent


@pytest.fixture
def mock_media_result():
    """Create a mock media search result."""
    media = MagicMock()
    media.title = "Test Movie"
    media.media_type = "movie"
    media.year = 2024
    media.original_title = None
    media.romaji_title = None
    return media


# =============================================================================
# WORKFLOW FIXTURES (for test_workflow.py compatibility)
# =============================================================================

@pytest.fixture
def mock_db():
    """Create mock async database session with proper async handling."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


def create_mock_result(return_value):
    """Helper to create a properly configured mock result for async db queries."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = return_value
    mock_result.scalars.return_value.all.return_value = []
    return mock_result


@pytest.fixture
def workflow_service(mock_db):
    """Create workflow service with mock db."""
    from app.services.workflow_service import WorkflowService
    return WorkflowService(mock_db)


# =============================================================================
# PLEX ACCESS FIXTURES (for test_plex_access.py compatibility)
# =============================================================================

@pytest.fixture
def mock_plex_resources_response():
    """Mock Plex.tv /resources API response with server access."""
    return [
        {
            "name": "Test Plex Server",
            "clientIdentifier": "test-machine-id-123",
            "provides": "server",
            "owned": True,
            "accessToken": "test-server-token"
        }
    ]


@pytest.fixture
def mock_plex_user_response():
    """Mock Plex.tv user account response."""
    return {
        "user": {
            "id": 12345678,
            "username": "PlexTestUser",
            "email": "plextest@example.com",
            "thumb": "https://plex.tv/users/avatar.png"
        }
    }


# =============================================================================
# CELERY FIXTURES
# =============================================================================

@pytest.fixture
def mock_celery_task():
    """Mock Celery task for testing without worker."""
    def _create_mock_task(return_value=None):
        mock_task = MagicMock()
        mock_task.delay.return_value = MagicMock(id="mock-task-id-123")
        mock_task.apply_async.return_value = MagicMock(id="mock-task-id-123")

        if return_value is not None:
            mock_task.return_value = return_value

        return mock_task

    return _create_mock_task
