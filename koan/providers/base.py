"""Base provider class."""

from __future__ import annotations

from typing import Any, AsyncIterator

from koan.types import Event, Message, ToolSchema


class BaseProvider:
    """Base class for LLM providers."""

    name: str = "base"

    def supports_tool_use(self) -> bool:
        return True

    def is_available(self) -> bool:
        return True

    async def stream(
        self, messages: list[Message], tools: list[ToolSchema]
    ) -> AsyncIterator[Event]:
        raise NotImplementedError
        yield  # make it an async generator
