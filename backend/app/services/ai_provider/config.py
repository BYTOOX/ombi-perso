"""
AI Provider configuration types and loading.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ProviderType(str, Enum):
    """Supported AI provider types."""
    LLAMA_CPP = "llama_cpp"      # llama.cpp server (OpenAI-compatible)
    OPENAI = "openai"            # OpenAI official API
    OPENROUTER = "openrouter"    # OpenRouter (multi-model gateway)


@dataclass
class AIConfig:
    """
    AI provider configuration.

    Loaded from database ServiceConfiguration for service_name="ai".
    """
    provider_type: ProviderType
    base_url: str
    api_key: Optional[str] = None
    model_scoring: Optional[str] = None
    model_rename: Optional[str] = None
    model_analysis: Optional[str] = None
    timeout: float = 120.0
    is_enabled: bool = True

    # Default model fallback
    default_model: str = field(default="qwen3-vl-30b")

    @property
    def models_endpoint(self) -> str:
        """
        Get the endpoint for listing models.

        OpenRouter uses /api/v1/models, others use /v1/models.
        """
        if self.provider_type == ProviderType.OPENROUTER:
            return "/api/v1/models"
        return "/v1/models"

    @property
    def chat_endpoint(self) -> str:
        """Get the chat completions endpoint (same for all providers)."""
        return "/v1/chat/completions"

    def get_model_for_task(self, task: str) -> str:
        """
        Get the configured model for a specific task.

        Args:
            task: One of 'scoring', 'rename', 'analysis'

        Returns:
            Model name to use for this task
        """
        if task == "scoring" and self.model_scoring:
            return self.model_scoring
        elif task == "rename" and self.model_rename:
            return self.model_rename
        elif task == "analysis" and self.model_analysis:
            return self.model_analysis

        # Fallback to scoring model, then default
        return self.model_scoring or self.default_model

    @property
    def requires_api_key(self) -> bool:
        """Check if this provider type requires an API key."""
        return self.provider_type in (ProviderType.OPENAI, ProviderType.OPENROUTER)

    def get_default_url(self) -> str:
        """Get the default URL for this provider type."""
        defaults = {
            ProviderType.LLAMA_CPP: "http://localhost:8080",
            ProviderType.OPENAI: "https://api.openai.com",
            ProviderType.OPENROUTER: "https://openrouter.ai",
        }
        return defaults.get(self.provider_type, "http://localhost:8080")
