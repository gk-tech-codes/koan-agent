"""OpenAI-compatible provider — works with Ollama, OpenAI, vLLM, LM Studio.

Adapted from claw-code openai_compat.rs: SSE streaming, tool call delta
assembly, retry on failure.
"""

from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator

import httpx

from koan.errors import MalformedToolCallError, ProviderError
from koan.providers.base import BaseProvider
from koan.types import (
    Event,
    EventType,
    Message,
    MessageRole,
    TokenUsage,
    ToolSchema,
)


def _format_messages(messages: list[Message]) -> list[dict[str, Any]]:
    """Convert our Message format to OpenAI chat format."""
    result = []
    for msg in messages:
        if msg.role == MessageRole.SYSTEM:
            text = " ".join(b.data.get("text", "") for b in msg.blocks)
            result.append({"role": "system", "content": text})
            continue

        if msg.role == MessageRole.USER:
            # Check for tool_result blocks
            tool_results = [b for b in msg.blocks if b.type == "tool_result"]
            if tool_results:
                for tr in tool_results:
                    result.append({
                        "role": "tool",
                        "tool_call_id": tr.data.get("tool_use_id", ""),
                        "content": tr.data.get("output", ""),
                    })
                continue
            text = " ".join(b.data.get("text", "") for b in msg.blocks if b.type == "text")
            result.append({"role": "user", "content": text})
            continue

        if msg.role == MessageRole.ASSISTANT:
            content_parts = []
            tool_calls = []
            for b in msg.blocks:
                if b.type == "text":
                    content_parts.append(b.data.get("text", ""))
                elif b.type == "tool_use":
                    tool_calls.append({
                        "id": b.data.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": b.data.get("name", ""),
                            "arguments": json.dumps(b.data.get("input", {})),
                        },
                    })
            entry: dict[str, Any] = {"role": "assistant"}
            text = " ".join(content_parts).strip()
            if text:
                entry["content"] = text
            if tool_calls:
                entry["tool_calls"] = tool_calls
                if "content" not in entry:
                    entry["content"] = ""
            else:
                entry.setdefault("content", "")
            result.append(entry)

    return result


def _format_tools(tools: list[ToolSchema]) -> list[dict[str, Any]]:
    """Convert our ToolSchema to OpenAI tool format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
            },
        }
        for t in tools
    ]


class OpenAICompatProvider(BaseProvider):
    """Provider for any OpenAI-compatible API (Ollama, OpenAI, vLLM, etc.)."""

    def __init__(self, name: str, endpoint: str, model: str, api_key: str = ""):
        self.name = name
        self._endpoint = endpoint
        self._model = model
        self._api_key = api_key

    def is_available(self) -> bool:
        try:
            # Quick check — just see if the endpoint responds
            with httpx.Client(timeout=3) as client:
                resp = client.get(self._endpoint.rsplit("/", 1)[0] + "/models")
                return resp.status_code < 500
        except Exception:
            return False

    async def stream(
        self, messages: list[Message], tools: list[ToolSchema]
    ) -> AsyncIterator[Event]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        body: dict[str, Any] = {
            "model": self._model,
            "messages": _format_messages(messages),
            "stream": True,
        }
        if tools:
            body["tools"] = _format_tools(tools)

        # Accumulate tool call deltas (same pattern as claw-code openai_compat.rs)
        tool_call_buffers: dict[int, dict[str, Any]] = {}
        text_buffer = ""

        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            try:
                async with client.stream("POST", self._endpoint, json=body, headers=headers) as resp:
                    if resp.status_code != 200:
                        error_body = ""
                        async for chunk in resp.aiter_text():
                            error_body += chunk
                        raise ProviderError(f"Provider returned {resp.status_code}: {error_body[:500]}")

                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data == "[DONE]":
                            break

                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue

                        choices = chunk.get("choices", [])
                        if not choices:
                            continue

                        delta = choices[0].get("delta", {})

                        # Text content
                        if "content" in delta and delta["content"]:
                            text_buffer += delta["content"]
                            yield Event(type=EventType.TEXT_DELTA, data={"text": delta["content"]})

                        # Tool call deltas — assemble incrementally
                        for tc in delta.get("tool_calls", []):
                            idx = tc.get("index", 0)
                            if idx not in tool_call_buffers:
                                tool_call_buffers[idx] = {
                                    "id": tc.get("id", f"call_{idx}"),
                                    "name": "",
                                    "arguments": "",
                                }
                            buf = tool_call_buffers[idx]
                            if tc.get("id"):
                                buf["id"] = tc["id"]
                            fn = tc.get("function", {})
                            if fn.get("name"):
                                buf["name"] += fn["name"]
                            if fn.get("arguments"):
                                buf["arguments"] += fn["arguments"]

                        # Usage
                        usage = chunk.get("usage")
                        if usage:
                            yield Event(
                                type=EventType.USAGE,
                                data={
                                    "input_tokens": usage.get("prompt_tokens", 0),
                                    "output_tokens": usage.get("completion_tokens", 0),
                                },
                            )

            except httpx.ConnectError as exc:
                raise ProviderError(f"Cannot connect to {self._endpoint}: {exc}") from exc

        # Emit assembled tool calls
        for idx in sorted(tool_call_buffers):
            buf = tool_call_buffers[idx]
            try:
                args = json.loads(buf["arguments"]) if buf["arguments"] else {}
            except json.JSONDecodeError as exc:
                raise MalformedToolCallError(
                    f"Malformed tool call JSON from {self.name}: {buf['arguments'][:200]}"
                ) from exc

            yield Event(
                type=EventType.TOOL_USE,
                data={"id": buf["id"], "name": buf["name"], "input": args},
            )

        yield Event(type=EventType.MESSAGE_STOP)
