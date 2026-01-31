"""
Tests for AI provider module.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx


class TestAIConfig:
    """Tests for AIConfig dataclass."""

    def test_models_endpoint_llama_cpp(self, ai_config):
        """llama.cpp uses /v1/models endpoint."""
        assert ai_config.models_endpoint == "/v1/models"

    def test_models_endpoint_openrouter(self, ai_config_openrouter):
        """OpenRouter uses /api/v1/models endpoint."""
        assert ai_config_openrouter.models_endpoint == "/api/v1/models"

    def test_chat_endpoint(self, ai_config):
        """All providers use /v1/chat/completions."""
        assert ai_config.chat_endpoint == "/v1/chat/completions"

    def test_get_model_for_task_scoring(self, ai_config):
        """Returns scoring model for scoring task."""
        assert ai_config.get_model_for_task("scoring") == "qwen3-vl-30b"

    def test_get_model_for_task_fallback(self):
        """Falls back to default_model when task model not set."""
        from app.services.ai_provider.config import AIConfig, ProviderType
        config = AIConfig(
            provider_type=ProviderType.LLAMA_CPP,
            base_url="http://localhost:8080",
            default_model="fallback-model"
        )
        assert config.get_model_for_task("scoring") == "fallback-model"

    def test_requires_api_key_openai(self, ai_config_openai):
        """OpenAI requires API key."""
        assert ai_config_openai.requires_api_key is True

    def test_requires_api_key_llama_cpp(self, ai_config):
        """llama.cpp does not require API key."""
        assert ai_config.requires_api_key is False


class TestOpenAICompatibleProvider:
    """Tests for OpenAICompatibleProvider."""

    @pytest.mark.asyncio
    async def test_list_models_success(self, ai_config, mock_httpx_response, mock_ai_models_response):
        """Successfully lists models from provider."""
        from app.services.ai_provider.provider import OpenAICompatibleProvider

        provider = OpenAICompatibleProvider(ai_config)

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.return_value = mock_httpx_response(200, mock_ai_models_response)

            models = await provider.list_models()

            assert len(models) == 2
            assert models[0].id == "qwen3-vl-30b"
            assert models[1].id == "llama-3-8b"

    @pytest.mark.asyncio
    async def test_list_models_openrouter_endpoint(self, ai_config_openrouter, mock_httpx_response, mock_ai_models_response):
        """OpenRouter uses correct /api/v1/models endpoint."""
        from app.services.ai_provider.provider import OpenAICompatibleProvider

        provider = OpenAICompatibleProvider(ai_config_openrouter)

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.return_value = mock_httpx_response(200, mock_ai_models_response)

            await provider.list_models()

            # Verify the correct endpoint was called
            call_args = mock_instance.get.call_args
            assert "/api/v1/models" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_list_models_timeout(self, ai_config):
        """Raises AITimeoutError on timeout."""
        from app.services.ai_provider.provider import OpenAICompatibleProvider
        from app.services.ai_provider.exceptions import AITimeoutError

        provider = OpenAICompatibleProvider(ai_config)

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.side_effect = httpx.TimeoutException("Timeout")

            with pytest.raises(AITimeoutError):
                await provider.list_models()

    @pytest.mark.asyncio
    async def test_chat_success(self, ai_config, mock_httpx_response, mock_chat_response):
        """Successfully sends chat request."""
        from app.services.ai_provider.provider import OpenAICompatibleProvider
        from app.services.ai_provider.base import ChatMessage

        provider = OpenAICompatibleProvider(ai_config)

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.post.return_value = mock_httpx_response(200, mock_chat_response)

            messages = [ChatMessage(role="user", content="Hello")]
            response = await provider.chat(messages)

            assert "rankings" in response.content
            assert response.model == "qwen3-vl-30b"

    @pytest.mark.asyncio
    async def test_chat_strips_thinking_tags(self, ai_config, mock_httpx_response, mock_chat_response_with_thinking):
        """Strips <think> tags from Qwen3 responses."""
        from app.services.ai_provider.provider import OpenAICompatibleProvider
        from app.services.ai_provider.base import ChatMessage

        provider = OpenAICompatibleProvider(ai_config)

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.post.return_value = mock_httpx_response(200, mock_chat_response_with_thinking)

            messages = [ChatMessage(role="user", content="Hello")]
            response = await provider.chat(messages)

            assert "<think>" not in response.content
            assert "rankings" in response.content

    @pytest.mark.asyncio
    async def test_chat_with_api_key(self, ai_config_openai, mock_httpx_response, mock_chat_response):
        """Includes API key in Authorization header."""
        from app.services.ai_provider.provider import OpenAICompatibleProvider
        from app.services.ai_provider.base import ChatMessage

        provider = OpenAICompatibleProvider(ai_config_openai)

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.post.return_value = mock_httpx_response(200, mock_chat_response)

            messages = [ChatMessage(role="user", content="Hello")]
            await provider.chat(messages)

            # Verify Authorization header was included
            call_kwargs = mock_instance.post.call_args[1]
            assert "Authorization" in call_kwargs["headers"]
            assert call_kwargs["headers"]["Authorization"] == "Bearer sk-test-key"

    @pytest.mark.asyncio
    async def test_health_check_available(self, ai_config, mock_httpx_response, mock_ai_models_response):
        """Health check returns available when models can be listed."""
        from app.services.ai_provider.provider import OpenAICompatibleProvider

        provider = OpenAICompatibleProvider(ai_config)

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.return_value = mock_httpx_response(200, mock_ai_models_response)

            result = await provider.health_check()

            assert result.available is True
            assert len(result.models) == 2
            assert result.latency_ms is not None

    @pytest.mark.asyncio
    async def test_health_check_disabled(self, ai_config):
        """Health check returns not available when disabled."""
        from app.services.ai_provider.provider import OpenAICompatibleProvider

        ai_config.is_enabled = False
        provider = OpenAICompatibleProvider(ai_config)

        result = await provider.health_check()

        assert result.available is False
        assert "disabled" in result.error.lower()


class TestAIProviderExceptions:
    """Tests for AI provider exceptions."""

    def test_not_configured_error(self):
        """AINotConfiguredError has correct message."""
        from app.services.ai_provider.exceptions import AINotConfiguredError

        error = AINotConfiguredError()
        assert "not configured" in str(error).lower()

    def test_timeout_error(self):
        """AITimeoutError includes timeout value."""
        from app.services.ai_provider.exceptions import AITimeoutError

        error = AITimeoutError(30.0)
        assert "30" in str(error)

    def test_response_error(self):
        """AIResponseError includes status code."""
        from app.services.ai_provider.exceptions import AIResponseError

        error = AIResponseError(status_code=500)
        assert "500" in str(error)


class TestAIService:
    """Tests for AIService facade."""

    @pytest.mark.asyncio
    async def test_is_available_when_configured(self, ai_config):
        """is_available returns True when configured."""
        from app.services.ai_provider import AIService

        service = AIService()

        with patch.object(service, "_load_config", return_value=ai_config):
            result = await service.is_available()
            assert result is True

    @pytest.mark.asyncio
    async def test_is_available_when_not_configured(self):
        """is_available returns False when not configured."""
        from app.services.ai_provider import AIService

        service = AIService()

        with patch.object(service, "_load_config", return_value=None):
            result = await service.is_available()
            assert result is False

    @pytest.mark.asyncio
    async def test_simple_score_torrents(self, mock_torrent_result, mock_media_result):
        """Simple scoring works without AI."""
        from app.services.ai_provider import AIService

        service = AIService()
        torrents = [mock_torrent_result]

        with patch.object(service, "is_available", return_value=False):
            result = service._simple_score_torrents(torrents, "1080p")

            assert len(result) == 1
            assert result[0].ai_score is not None
            assert result[0].ai_score > 0

    def test_extract_season_episode(self):
        """Extracts season/episode from various formats."""
        from app.services.ai_provider import AIService

        service = AIService()

        # S01E01 format
        result = service._extract_season_episode("Show.S01E05.1080p.mkv")
        assert result == (1, 5)

        # 1x01 format
        result = service._extract_season_episode("Show.1x05.720p.mkv")
        assert result == (1, 5)

        # No match
        result = service._extract_season_episode("Movie.2024.1080p.mkv")
        assert result is None

    def test_sanitize_filename(self):
        """Removes invalid filename characters."""
        from app.services.ai_provider import AIService

        service = AIService()

        result = service._sanitize_filename('Movie: The "Sequel" (2024)')
        assert ":" not in result
        assert '"' not in result
