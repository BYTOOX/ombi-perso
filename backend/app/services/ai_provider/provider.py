"""
OpenAI-compatible AI provider implementation.

Supports:
- llama.cpp server
- llama-cpp-python server
- OpenAI API
- OpenRouter
"""
import logging
import re
import time
from typing import Any, Dict, List, Optional

import httpx

from .base import AIProvider, ChatMessage, ChatResponse, HealthCheckResult, ModelInfo
from .config import AIConfig, ProviderType
from .exceptions import AIDisabledError, AINotConfiguredError, AIResponseError, AITimeoutError

logger = logging.getLogger(__name__)

# Number of retries for transient errors
MAX_RETRIES = 2
RETRY_DELAY = 1.0  # seconds


class OpenAICompatibleProvider(AIProvider):
    """
    Unified provider for all OpenAI-compatible APIs.

    Handles the differences between providers:
    - Different models endpoint for OpenRouter (/api/v1/models vs /v1/models)
    - API key handling (Bearer token)
    - Response parsing and error handling
    """

    def __init__(self, config: AIConfig):
        """
        Initialize the provider with configuration.

        Args:
            config: AIConfig with provider settings
        """
        self.config = config
        self._validate_config()

    def _validate_config(self):
        """Validate the configuration."""
        if not self.config.base_url:
            raise AINotConfiguredError("Base URL is required")

        if self.config.requires_api_key and not self.config.api_key:
            raise AINotConfiguredError(
                f"API key is required for {self.config.provider_type.value}"
            )

    def _build_headers(self) -> Dict[str, str]:
        """Build HTTP headers for requests."""
        headers = {"Content-Type": "application/json"}

        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        # OpenRouter-specific headers
        if self.config.provider_type == ProviderType.OPENROUTER:
            headers["HTTP-Referer"] = "https://plex-kiosk.local"
            headers["X-Title"] = "Plex Kiosk"

        return headers

    def _get_base_url(self) -> str:
        """Get the base URL, ensuring no trailing slash."""
        return self.config.base_url.rstrip("/")

    async def list_models(self) -> List[ModelInfo]:
        """
        List available models from the provider.

        Returns:
            List of ModelInfo objects
        """
        if not self.config.is_enabled:
            raise AIDisabledError()

        url = f"{self._get_base_url()}{self.config.models_endpoint}"
        headers = self._build_headers()

        logger.info(f"[AI] Listing models from: {url}")

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, headers=headers)

            response.raise_for_status()
            data = response.json()

            models = []
            for model_data in data.get("data", []):
                models.append(ModelInfo(
                    id=model_data.get("id", "unknown"),
                    owned_by=model_data.get("owned_by"),
                    created=model_data.get("created")
                ))

            logger.info(f"[AI] Found {len(models)} models")
            return models

        except httpx.TimeoutException as e:
            logger.error(f"[AI] Timeout listing models: {e}")
            raise AITimeoutError(15.0)
        except httpx.HTTPStatusError as e:
            logger.error(f"[AI] HTTP error listing models: {e.response.status_code}")
            raise AIResponseError(
                status_code=e.response.status_code,
                response_body=e.response.text[:500]
            )
        except Exception as e:
            logger.error(f"[AI] Error listing models: {e}")
            raise AIResponseError(message=str(e))

    async def chat(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> ChatResponse:
        """
        Send a chat completion request.

        Args:
            messages: List of ChatMessage objects
            model: Model to use (uses config default if not specified)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            ChatResponse with the generated content
        """
        if not self.config.is_enabled:
            raise AIDisabledError()

        url = f"{self._get_base_url()}{self.config.chat_endpoint}"
        headers = self._build_headers()
        model_to_use = model or self.config.default_model

        logger.info(f"[AI] Chat request to: {url}")
        logger.info(f"[AI] Model: {model_to_use}")

        payload = {
            "model": model_to_use,
            "messages": [m.to_dict() if isinstance(m, ChatMessage) else m for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False
        }

        last_error = None

        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"[AI] Attempt {attempt + 1}/{MAX_RETRIES} (timeout: {self.config.timeout}s)")

                async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                    response = await client.post(url, headers=headers, json=payload)

                logger.info(f"[AI] Response status: {response.status_code}")
                response.raise_for_status()

                data = response.json()
                content = self._extract_content(data)

                return ChatResponse(
                    content=content,
                    model=data.get("model", model_to_use),
                    usage=data.get("usage"),
                    raw_response=data
                )

            except httpx.TimeoutException as e:
                logger.warning(f"[AI] Timeout on attempt {attempt + 1}: {e}")
                last_error = AITimeoutError(self.config.timeout)
                if attempt < MAX_RETRIES - 1:
                    await self._retry_delay()

            except httpx.HTTPStatusError as e:
                logger.error(f"[AI] HTTP error: {e.response.status_code}")
                # Don't retry on 4xx errors (client errors)
                if 400 <= e.response.status_code < 500:
                    raise AIResponseError(
                        status_code=e.response.status_code,
                        response_body=e.response.text[:500]
                    )
                last_error = AIResponseError(
                    status_code=e.response.status_code,
                    response_body=e.response.text[:500]
                )
                if attempt < MAX_RETRIES - 1:
                    await self._retry_delay()

            except Exception as e:
                logger.error(f"[AI] Error on attempt {attempt + 1}: {e}")
                last_error = AIResponseError(message=str(e))
                if attempt < MAX_RETRIES - 1:
                    await self._retry_delay()

        # All retries failed
        if last_error:
            raise last_error
        raise AIResponseError(message="Unknown error after retries")

    def _extract_content(self, data: Dict[str, Any]) -> str:
        """
        Extract content from API response.

        Handles:
        - Standard OpenAI response format
        - Qwen3 <think>...</think> tags removal
        """
        choices = data.get("choices", [])
        if not choices:
            raise AIResponseError(message="No choices in response")

        content = choices[0].get("message", {}).get("content", "")

        # Strip <think>...</think> tags from Qwen3 responses
        if "<think>" in content:
            original_len = len(content)
            content = re.sub(r'<think>[\s\S]*?</think>', '', content, flags=re.IGNORECASE)
            content = content.strip()
            logger.info(f"[AI] Stripped thinking tags: {original_len} → {len(content)} chars")

        return content

    async def _retry_delay(self):
        """Wait before retrying."""
        import asyncio
        await asyncio.sleep(RETRY_DELAY)

    async def health_check(self) -> HealthCheckResult:
        """
        Check if the provider is available and healthy.

        Returns:
            HealthCheckResult with status and available models
        """
        if not self.config.base_url:
            return HealthCheckResult(
                available=False,
                error="URL not configured"
            )

        if not self.config.is_enabled:
            return HealthCheckResult(
                available=False,
                error="Service disabled"
            )

        start_time = time.time()

        try:
            models = await self.list_models()
            latency_ms = int((time.time() - start_time) * 1000)

            return HealthCheckResult(
                available=True,
                models=[m.id for m in models],
                configured_model=self.config.default_model,
                latency_ms=latency_ms
            )

        except AITimeoutError:
            return HealthCheckResult(
                available=False,
                error="Timeout"
            )
        except AIResponseError as e:
            return HealthCheckResult(
                available=False,
                error=e.message
            )
        except Exception as e:
            return HealthCheckResult(
                available=False,
                error=str(e)
            )
