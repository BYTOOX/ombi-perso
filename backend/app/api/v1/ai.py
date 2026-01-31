"""
AI Admin API endpoints.

Provides endpoints for:
- GET/PUT AI settings
- Testing AI connection
- Listing available models
"""
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ...models.user import User
from ...services.ai_provider import (
    AINotConfiguredError,
    ProviderType,
    get_ai_service,
)
from ...services.service_config_service import get_service_config_service
from .auth import get_current_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/ai", tags=["AI Admin"])


# =============================================================================
# SCHEMAS
# =============================================================================


class AISettingsResponse(BaseModel):
    """Response schema for AI settings (without secrets)."""
    provider_type: Optional[str] = None
    base_url: Optional[str] = None
    has_api_key: bool = False
    model_scoring: Optional[str] = None
    model_rename: Optional[str] = None
    model_analysis: Optional[str] = None
    timeout: float = 120.0
    is_enabled: bool = False
    is_configured: bool = False


class AISettingsUpdate(BaseModel):
    """Schema for updating AI settings."""
    provider_type: Optional[str] = Field(
        None,
        description="Provider type: llama_cpp, openai, or openrouter"
    )
    base_url: Optional[str] = Field(
        None,
        description="Base URL of the AI service"
    )
    api_key: Optional[str] = Field(
        None,
        description="API key (will be encrypted)"
    )
    model_scoring: Optional[str] = Field(
        None,
        description="Model to use for torrent scoring"
    )
    model_rename: Optional[str] = Field(
        None,
        description="Model to use for file renaming"
    )
    model_analysis: Optional[str] = Field(
        None,
        description="Model to use for library analysis"
    )
    timeout: Optional[float] = Field(
        None,
        ge=10,
        le=600,
        description="Request timeout in seconds (10-600)"
    )
    is_enabled: Optional[bool] = Field(
        None,
        description="Whether the service is enabled"
    )


class AITestRequest(BaseModel):
    """Schema for testing AI connection with custom settings."""
    provider_type: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None


class ModelInfo(BaseModel):
    """Information about an available model."""
    id: str
    owned_by: Optional[str] = None


class AITestResponse(BaseModel):
    """Response schema for AI connection test."""
    status: str
    message: str
    models: List[ModelInfo] = []
    latency_ms: Optional[int] = None


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.get("/settings", response_model=AISettingsResponse)
async def get_ai_settings(
    admin: User = Depends(get_current_admin)
) -> AISettingsResponse:
    """
    Get current AI settings (without secrets).

    Returns the current AI configuration with api_key masked.
    """
    config_service = get_service_config_service()
    db_config = await config_service.get_service_config("ai")

    if not db_config:
        return AISettingsResponse(is_configured=False, is_enabled=False)

    extra = db_config.extra_config or {}

    return AISettingsResponse(
        provider_type=extra.get("provider_type", "llama_cpp"),
        base_url=db_config.url,
        has_api_key=bool(db_config.api_key_encrypted),
        model_scoring=extra.get("model_scoring"),
        model_rename=extra.get("model_rename"),
        model_analysis=extra.get("model_analysis"),
        timeout=extra.get("timeout", 120.0),
        is_enabled=db_config.is_enabled,
        is_configured=bool(db_config.url)
    )


@router.put("/settings", response_model=AISettingsResponse)
async def update_ai_settings(
    settings: AISettingsUpdate,
    admin: User = Depends(get_current_admin)
) -> AISettingsResponse:
    """
    Update AI settings.

    Saves the new configuration to the database.
    API key is encrypted before storage.
    """
    config_service = get_service_config_service()

    # Get current config or create new
    current = await config_service.get_service_config("ai")
    extra = current.extra_config.copy() if current and current.extra_config else {}

    # Update extra_config fields
    if settings.provider_type is not None:
        # Validate provider type
        try:
            ProviderType(settings.provider_type)
            extra["provider_type"] = settings.provider_type
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid provider_type. Must be one of: {[p.value for p in ProviderType]}"
            )

    if settings.model_scoring is not None:
        extra["model_scoring"] = settings.model_scoring

    if settings.model_rename is not None:
        extra["model_rename"] = settings.model_rename

    if settings.model_analysis is not None:
        extra["model_analysis"] = settings.model_analysis

    if settings.timeout is not None:
        extra["timeout"] = settings.timeout

    # Update service config
    await config_service.set_service_config(
        service_name="ai",
        url=settings.base_url if settings.base_url is not None else (current.url if current else None),
        api_key=settings.api_key,  # Will be encrypted by config service
        extra_config=extra,
        is_enabled=settings.is_enabled if settings.is_enabled is not None else (current.is_enabled if current else True)
    )

    # Invalidate AI service cache
    ai_service = get_ai_service()
    ai_service.invalidate_cache()

    logger.info(f"[AI] Settings updated by admin {admin.username}")

    # Return updated settings
    return await get_ai_settings(admin)


@router.post("/test", response_model=AITestResponse)
async def test_ai_connection(
    test_config: Optional[AITestRequest] = None,
    admin: User = Depends(get_current_admin)
) -> AITestResponse:
    """
    Test AI connection and list available models.

    If test_config is provided, uses those settings for the test.
    Otherwise, uses the saved configuration.
    """
    import httpx
    from ...services.ai_provider.config import AIConfig, ProviderType
    from ...services.ai_provider.provider import OpenAICompatibleProvider

    start_time = time.time()

    try:
        if test_config and (test_config.base_url or test_config.api_key):
            # Use provided test config
            config_service = get_service_config_service()
            current = await config_service.get_service_config("ai")
            extra = current.extra_config if current and current.extra_config else {}

            provider_type_str = test_config.provider_type or extra.get("provider_type", "llama_cpp")
            try:
                provider_type = ProviderType(provider_type_str)
            except ValueError:
                provider_type = ProviderType.LLAMA_CPP

            config = AIConfig(
                provider_type=provider_type,
                base_url=(test_config.base_url or (current.url if current else "")).rstrip("/"),
                api_key=test_config.api_key or (await config_service.get_decrypted_value("ai", "api_key") if current else None),
                timeout=extra.get("timeout", 120.0),
                is_enabled=True
            )

            if not config.base_url:
                return AITestResponse(
                    status="error",
                    message="No URL configured"
                )

            provider = OpenAICompatibleProvider(config)

        else:
            # Use saved config
            ai_service = get_ai_service()

            try:
                provider = await ai_service._get_provider()
            except AINotConfiguredError:
                return AITestResponse(
                    status="error",
                    message="AI service not configured. Please provide URL."
                )

        # List models
        models = await provider.list_models()
        latency_ms = int((time.time() - start_time) * 1000)

        logger.info(f"[AI] Test successful: {len(models)} models found in {latency_ms}ms")

        return AITestResponse(
            status="ok",
            message=f"Connected! {len(models)} model(s) available.",
            models=[ModelInfo(id=m.id, owned_by=m.owned_by) for m in models],
            latency_ms=latency_ms
        )

    except httpx.TimeoutException:
        return AITestResponse(
            status="error",
            message="Connection timeout. Check if the server is running."
        )

    except httpx.ConnectError as e:
        return AITestResponse(
            status="error",
            message=f"Connection failed: {str(e)}"
        )

    except Exception as e:
        logger.error(f"[AI] Test failed: {e}")
        return AITestResponse(
            status="error",
            message=str(e)
        )


@router.get("/models", response_model=List[ModelInfo])
async def list_ai_models(
    admin: User = Depends(get_current_admin)
) -> List[ModelInfo]:
    """
    List available models from the configured AI provider.

    Uses the saved configuration.
    """
    ai_service = get_ai_service()

    try:
        models = await ai_service.list_models()
        return [ModelInfo(id=m.id, owned_by=m.owned_by) for m in models]

    except AINotConfiguredError:
        raise HTTPException(
            status_code=400,
            detail="AI service not configured"
        )

    except Exception as e:
        logger.error(f"[AI] Failed to list models: {e}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@router.get("/health")
async def get_ai_health(
    admin: User = Depends(get_current_admin)
) -> Dict[str, Any]:
    """
    Get AI service health status.

    Returns availability, configured model, and error if any.
    """
    ai_service = get_ai_service()
    return await ai_service.health_check()
