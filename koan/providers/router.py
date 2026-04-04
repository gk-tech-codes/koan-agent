"""Provider router — multi-provider routing with automatic fallback.

Adapted from claw-code client.rs: provider detection + delegation.
Extended with routing strategies and fallback on tool-call failures.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, AsyncIterator

from koan.errors import MalformedToolCallError, ProviderError
from koan.providers.base import BaseProvider
from koan.types import Event, EventType, Message, ToolSchema


class RoutingStrategy(Enum):
    LOCAL_FIRST = "local_first"      # try local, fallback to cloud on failure
    CLOUD_ONLY = "cloud_only"        # always use the configured default
    FALLBACK_ONLY = "fallback_only"  # always use the fallback provider
    COST_AWARE = "cost_aware"        # route by estimated cost (future)


class ProviderRouter(BaseProvider):
    """Routes requests across multiple providers with fallback.

    Strategies:
      local_first  — try primary (e.g. Ollama), fall back to cloud on failure
      cloud_only   — always use primary, no fallback
      cost_aware   — (future) route by estimated cost vs budget
    """

    def __init__(
        self,
        primary: BaseProvider,
        fallback: BaseProvider | None = None,
        strategy: RoutingStrategy = RoutingStrategy.LOCAL_FIRST,
    ):
        self.name = f"router({primary.name}→{fallback.name if fallback else 'none'})"
        self._model = getattr(primary, '_model', 'unknown')
        self._primary = primary
        self._fallback = fallback
        self._strategy = strategy
        self._primary_failures = 0
        self._fallback_uses = 0

    def is_available(self) -> bool:
        return self._primary.is_available() or (
            self._fallback is not None and self._fallback.is_available()
        )

    def stats(self) -> dict:
        return {
            "primary": self._primary.name,
            "fallback": self._fallback.name if self._fallback else None,
            "strategy": self._strategy.value,
            "primary_failures": self._primary_failures,
            "fallback_uses": self._fallback_uses,
        }

    async def stream(
        self, messages: list[Message], tools: list[ToolSchema]
    ) -> AsyncIterator[Event]:
        if self._strategy == RoutingStrategy.FALLBACK_ONLY and self._fallback:
            async for event in self._fallback.stream(messages, tools):
                yield event
            return

        # Try primary first
        try:
            async for event in self._primary.stream(messages, tools):
                yield event
            return

        except MalformedToolCallError as exc:
            # Primary returned bad tool JSON — retry with fallback
            self._primary_failures += 1
            if self._fallback and self._strategy in (
                RoutingStrategy.LOCAL_FIRST, RoutingStrategy.COST_AWARE
            ):
                self._fallback_uses += 1
                async for event in self._fallback.stream(messages, tools):
                    yield event
                return
            raise

        except ProviderError as exc:
            # Primary is down or errored — try fallback
            self._primary_failures += 1
            if self._fallback and self._strategy in (
                RoutingStrategy.LOCAL_FIRST, RoutingStrategy.COST_AWARE
            ):
                self._fallback_uses += 1
                try:
                    async for event in self._fallback.stream(messages, tools):
                        yield event
                    return
                except ProviderError:
                    # Both failed — raise the original error
                    raise exc
            raise
