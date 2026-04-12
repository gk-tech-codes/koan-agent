"""Server provider — sends messages to enterprise server instead of LLM directly.

Used when koan runs in --server mode. The enterprise server handles
LLM routing, tool execution, and token tracking.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from koan.errors import ProviderError
from koan.log import get_logger
from koan.providers.base import BaseProvider
from koan.types import Event, EventType, Message, ToolSchema

log = get_logger("server_provider")


class ServerProvider(BaseProvider):
    """Sends chat to enterprise server. Server handles everything."""

    def __init__(self, url: str, client_id: str):
        self.name = "server"
        self._model = "server"
        self._url = url.rstrip("/")
        self._client_id = client_id

    def is_available(self) -> bool:
        try:
            r = httpx.get(f"{self._url}/health", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    async def stream(
        self, messages: list[Message], tools: list[ToolSchema]
    ) -> AsyncIterator[Event]:
        """Send to enterprise server, get response, emit as events."""
        # Extract the latest user message
        user_msg = ""
        for m in reversed(messages):
            if m.role.value == "user":
                for b in m.blocks:
                    if b.type == "text":
                        user_msg = b.data.get("text", "")
                        break
                if user_msg:
                    break

        if not user_msg:
            yield Event(type=EventType.TEXT_DELTA, data={"text": "No message to send."})
            yield Event(type=EventType.MESSAGE_STOP)
            return

        log.debug("Sending to server: %s", user_msg[:80])

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
                r = await client.post(
                    f"{self._url}/chat",
                    json={"message": user_msg, "session_id": self._client_id},
                )

                if r.status_code != 200:
                    raise ProviderError(f"Server returned {r.status_code}: {r.text[:200]}")

                data = r.json()

                # Emit response as text delta
                response_text = data.get("response", "")
                if response_text:
                    yield Event(type=EventType.TEXT_DELTA, data={"text": response_text})

                # Emit usage
                tokens = data.get("tokens", {})
                if tokens:
                    yield Event(type=EventType.USAGE, data={
                        "input_tokens": tokens.get("cumulative", 0),
                        "output_tokens": 0,
                    })

        except httpx.ConnectError as exc:
            raise ProviderError(f"Cannot connect to server {self._url}: {exc}") from exc
        except httpx.ReadTimeout as exc:
            raise ProviderError(f"Server timeout: {exc}") from exc

        yield Event(type=EventType.MESSAGE_STOP)
