"""
Pytest configuration and shared fixtures.
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Set test environment
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars"
os.environ["DATABASE_URL"] = "sqlite:///./test.db"


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
