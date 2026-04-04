"""Error hierarchy for Kōan."""

from __future__ import annotations


class KoanError(Exception):
    """Base error for all Kōan errors."""


class ConfigError(KoanError):
    """Configuration loading or validation failed."""


class ProviderError(KoanError):
    """Provider communication failed."""


class MalformedToolCallError(ProviderError):
    """LLM returned invalid tool call JSON."""


class ToolError(KoanError):
    """Tool execution failed."""


class PermissionDenied(KoanError):
    """Tool use was denied by the permission system."""


class MemoryError(KoanError):
    """Memory store operation failed."""


class SessionError(KoanError):
    """Session persistence failed."""
