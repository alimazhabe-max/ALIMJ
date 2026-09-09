"""Application-specific exception hierarchy.

The hierarchy is intentionally small and dependency-free so lower-level utils can
raise precise errors without importing Telegram handlers or service modules.
"""
from __future__ import annotations


class ALIMJError(Exception):
    """Base exception for expected application-level failures."""


class ConfigurationError(ALIMJError):
    """Invalid or incomplete runtime configuration."""


class ValidationError(ALIMJError):
    """Invalid user or service input."""


class NetworkError(ALIMJError):
    """External network/service failure."""


class RateLimitError(NetworkError):
    """Remote service temporarily rejected a request because of rate limits."""


class AccessDeniedError(NetworkError):
    """Remote service refused access (for example HTTP 401/403/451)."""


class UpstreamTimeoutError(NetworkError):
    """Remote service did not answer within the configured timeout."""


class AIError(ALIMJError):
    """Base class for AI-related failures."""


class AIProviderError(AIError):
    """An AI provider failed or returned an unusable response."""


class AIQuotaError(AIProviderError):
    """An AI provider reported quota/rate exhaustion."""


class DatabaseError(ALIMJError):
    """Database operation failed."""


class ToolError(ALIMJError):
    """AI tool execution failed in an expected way."""
