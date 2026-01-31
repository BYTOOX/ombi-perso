"""
Tests for AI admin API endpoints.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestAISettingsEndpoint:
    """Tests for GET/PUT /admin/ai/settings endpoints."""

    @pytest.mark.asyncio
    async def test_get_settings_not_configured(self):
        """Returns empty settings when not configured."""
        from app.api.v1.ai import get_ai_settings

        mock_admin = MagicMock()
        mock_config_service = MagicMock()
        mock_config_service.get_service_config = AsyncMock(return_value=None)

        with patch("app.api.v1.ai.get_service_config_service", return_value=mock_config_service):
            result = await get_ai_settings(mock_admin)

            assert result.is_configured is False
            assert result.is_enabled is False

    @pytest.mark.asyncio
    async def test_get_settings_configured(self):
        """Returns settings when configured."""
        from app.api.v1.ai import get_ai_settings

        mock_admin = MagicMock()
        mock_db_config = MagicMock()
        mock_db_config.url = "http://localhost:8080"
        mock_db_config.api_key_encrypted = "encrypted_key"
        mock_db_config.is_enabled = True
        mock_db_config.extra_config = {
            "provider_type": "llama_cpp",
            "model_scoring": "qwen3-vl-30b",
            "timeout": 120.0
        }

        mock_config_service = MagicMock()
        mock_config_service.get_service_config = AsyncMock(return_value=mock_db_config)

        with patch("app.api.v1.ai.get_service_config_service", return_value=mock_config_service):
            result = await get_ai_settings(mock_admin)

            assert result.is_configured is True
            assert result.is_enabled is True
            assert result.has_api_key is True
            assert result.provider_type == "llama_cpp"
            assert result.model_scoring == "qwen3-vl-30b"


class TestAITestEndpoint:
    """Tests for POST /admin/ai/test endpoint."""

    @pytest.mark.asyncio
    async def test_test_connection_success(self, mock_ai_models_response):
        """Returns OK and models on successful test."""
        from app.api.v1.ai import test_ai_connection, AITestRequest
        from app.services.ai_provider.base import ModelInfo

        mock_admin = MagicMock()
        mock_provider = AsyncMock()
        mock_provider.list_models.return_value = [
            ModelInfo(id="qwen3-vl-30b", owned_by="local"),
            ModelInfo(id="llama-3-8b", owned_by="local")
        ]

        mock_ai_service = MagicMock()
        mock_ai_service._get_provider = AsyncMock(return_value=mock_provider)

        with patch("app.api.v1.ai.get_ai_service", return_value=mock_ai_service):
            result = await test_ai_connection(None, mock_admin)

            assert result.status == "ok"
            assert len(result.models) == 2
            assert result.latency_ms is not None

    @pytest.mark.asyncio
    async def test_test_connection_not_configured(self):
        """Returns error when not configured."""
        from app.api.v1.ai import test_ai_connection
        from app.services.ai_provider.exceptions import AINotConfiguredError

        mock_admin = MagicMock()
        mock_ai_service = MagicMock()
        mock_ai_service._get_provider = AsyncMock(side_effect=AINotConfiguredError())

        with patch("app.api.v1.ai.get_ai_service", return_value=mock_ai_service):
            result = await test_ai_connection(None, mock_admin)

            assert result.status == "error"
            assert "not configured" in result.message.lower()

    @pytest.mark.asyncio
    async def test_test_connection_with_custom_config(self, mock_ai_models_response):
        """Uses custom config when provided."""
        from app.api.v1.ai import test_ai_connection, AITestRequest
        from app.services.ai_provider.base import ModelInfo

        mock_admin = MagicMock()

        # Mock config service
        mock_config_service = MagicMock()
        mock_config_service.get_service_config = AsyncMock(return_value=None)
        mock_config_service.get_decrypted_value = AsyncMock(return_value=None)

        # Mock httpx response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_ai_models_response
        mock_response.raise_for_status = MagicMock()

        with patch("app.api.v1.ai.get_service_config_service", return_value=mock_config_service), \
             patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.return_value = mock_response

            test_config = AITestRequest(
                provider_type="llama_cpp",
                base_url="http://custom:8080",
                api_key=None
            )

            result = await test_ai_connection(test_config, mock_admin)

            assert result.status == "ok"


class TestAIModelsEndpoint:
    """Tests for GET /admin/ai/models endpoint."""

    @pytest.mark.asyncio
    async def test_list_models_success(self):
        """Returns model list on success."""
        from app.api.v1.ai import list_ai_models
        from app.services.ai_provider.base import ModelInfo

        mock_admin = MagicMock()
        mock_ai_service = MagicMock()
        mock_ai_service.list_models = AsyncMock(return_value=[
            ModelInfo(id="model-1", owned_by="local"),
            ModelInfo(id="model-2", owned_by="openai")
        ])

        with patch("app.api.v1.ai.get_ai_service", return_value=mock_ai_service):
            result = await list_ai_models(mock_admin)

            assert len(result) == 2
            assert result[0].id == "model-1"

    @pytest.mark.asyncio
    async def test_list_models_not_configured(self):
        """Raises 400 when not configured."""
        from app.api.v1.ai import list_ai_models
        from app.services.ai_provider.exceptions import AINotConfiguredError
        from fastapi import HTTPException

        mock_admin = MagicMock()
        mock_ai_service = MagicMock()
        mock_ai_service.list_models = AsyncMock(side_effect=AINotConfiguredError())

        with patch("app.api.v1.ai.get_ai_service", return_value=mock_ai_service):
            with pytest.raises(HTTPException) as exc_info:
                await list_ai_models(mock_admin)

            assert exc_info.value.status_code == 400


class TestAIHealthEndpoint:
    """Tests for GET /admin/ai/health endpoint."""

    @pytest.mark.asyncio
    async def test_health_available(self):
        """Returns available status when healthy."""
        from app.api.v1.ai import get_ai_health

        mock_admin = MagicMock()
        mock_ai_service = MagicMock()
        mock_ai_service.health_check = AsyncMock(return_value={
            "available": True,
            "models": ["model-1", "model-2"],
            "configured_model": "model-1"
        })

        with patch("app.api.v1.ai.get_ai_service", return_value=mock_ai_service):
            result = await get_ai_health(mock_admin)

            assert result["available"] is True
            assert len(result["models"]) == 2

    @pytest.mark.asyncio
    async def test_health_unavailable(self):
        """Returns error when not available."""
        from app.api.v1.ai import get_ai_health

        mock_admin = MagicMock()
        mock_ai_service = MagicMock()
        mock_ai_service.health_check = AsyncMock(return_value={
            "available": False,
            "error": "Connection refused"
        })

        with patch("app.api.v1.ai.get_ai_service", return_value=mock_ai_service):
            result = await get_ai_health(mock_admin)

            assert result["available"] is False
            assert "error" in result
