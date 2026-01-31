"""
Custom exceptions for AI provider module.
"""


class AIError(Exception):
    """Base exception for AI-related errors."""
    pass


class AINotConfiguredError(AIError):
    """Raised when AI service is not configured."""

    def __init__(self, message: str = "AI service not configured. Please configure it in admin settings."):
        self.message = message
        super().__init__(self.message)


class AITimeoutError(AIError):
    """Raised when AI request times out."""

    def __init__(self, timeout: float, message: str = None):
        self.timeout = timeout
        self.message = message or f"AI request timed out after {timeout} seconds"
        super().__init__(self.message)


class AIResponseError(AIError):
    """Raised when AI returns an invalid or error response."""

    def __init__(self, status_code: int = None, message: str = None, response_body: str = None):
        self.status_code = status_code
        self.response_body = response_body
        self.message = message or f"AI response error (HTTP {status_code})"
        super().__init__(self.message)


class AIDisabledError(AIError):
    """Raised when AI service is disabled."""

    def __init__(self, message: str = "AI service is disabled"):
        self.message = message
        super().__init__(self.message)
