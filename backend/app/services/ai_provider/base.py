"""
Base types and protocol for AI providers.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Union


@dataclass
class ChatMessage:
    """
    A chat message for the AI provider.

    Attributes:
        role: Message role - 'system', 'user', or 'assistant'
        content: Message content - string for text, list for multimodal (vision)
    """
    role: str
    content: Union[str, List[Dict[str, Any]]]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API payload."""
        return {
            "role": self.role,
            "content": self.content
        }


@dataclass
class ChatResponse:
    """
    Response from AI chat completion.

    Attributes:
        content: The generated text response
        model: Model that generated the response
        usage: Token usage information (optional)
        raw_response: Full raw response from the API (optional)
    """
    content: str
    model: str
    usage: Optional[Dict[str, int]] = None
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class ModelInfo:
    """
    Information about an available model.

    Attributes:
        id: Model identifier
        owned_by: Organization that owns/provides the model
        created: Creation timestamp (optional)
    """
    id: str
    owned_by: Optional[str] = None
    created: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "owned_by": self.owned_by,
            "created": self.created
        }


@dataclass
class HealthCheckResult:
    """
    Result of a health check on the AI provider.

    Attributes:
        available: Whether the service is available
        models: List of available models (if available)
        configured_model: Currently configured model
        error: Error message if not available
        latency_ms: Response latency in milliseconds
    """
    available: bool
    models: List[str] = field(default_factory=list)
    configured_model: Optional[str] = None
    error: Optional[str] = None
    latency_ms: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "available": self.available,
            "models": self.models,
        }
        if self.configured_model:
            result["configured_model"] = self.configured_model
        if self.error:
            result["error"] = self.error
        if self.latency_ms is not None:
            result["latency_ms"] = self.latency_ms
        return result


class AIProvider(Protocol):
    """
    Protocol defining the interface for AI providers.

    All AI providers must implement these methods to be compatible
    with the AIService facade.
    """

    async def list_models(self) -> List[ModelInfo]:
        """
        List available models from the provider.

        Returns:
            List of ModelInfo objects for available models

        Raises:
            AINotConfiguredError: If provider is not configured
            AIResponseError: If provider returns an error
            AITimeoutError: If request times out
        """
        ...

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
            messages: List of chat messages
            model: Model to use (optional, uses default if not specified)
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate

        Returns:
            ChatResponse with the generated content

        Raises:
            AINotConfiguredError: If provider is not configured
            AIResponseError: If provider returns an error
            AITimeoutError: If request times out
        """
        ...

    async def health_check(self) -> HealthCheckResult:
        """
        Check if the provider is available and healthy.

        Returns:
            HealthCheckResult with availability status and model list
        """
        ...
