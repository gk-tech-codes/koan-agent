"""AWS Bedrock provider — uses boto3 converse_stream API.

Supports Claude models via Bedrock with optional role assumption.
Streams text deltas in real-time, collects tool calls at block boundaries.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

from koan.errors import ProviderError
from koan.providers.base import BaseProvider
from koan.types import Event, EventType, Message, MessageRole, ToolSchema


def _format_messages(messages: list[Message]) -> tuple:
    system = []
    converse_msgs = []

    for msg in messages:
        if msg.role == MessageRole.SYSTEM:
            text = " ".join(b.data.get("text", "") for b in msg.blocks)
            system.append({"text": text})
            continue

        if msg.role == MessageRole.USER:
            tool_results = [b for b in msg.blocks if b.type == "tool_result"]
            if tool_results:
                content = []
                for tr in tool_results:
                    content.append({
                        "toolResult": {
                            "toolUseId": tr.data.get("tool_use_id", ""),
                            "content": [{"text": tr.data.get("output", "")}],
                            "status": "error" if tr.data.get("is_error") else "success",
                        }
                    })
                converse_msgs.append({"role": "user", "content": content})
                continue
            text = " ".join(b.data.get("text", "") for b in msg.blocks if b.type == "text")
            converse_msgs.append({"role": "user", "content": [{"text": text}]})
            continue

        if msg.role == MessageRole.ASSISTANT:
            content = []
            for b in msg.blocks:
                if b.type == "text" and b.data.get("text", "").strip():
                    content.append({"text": b.data["text"]})
                elif b.type == "tool_use":
                    content.append({
                        "toolUse": {
                            "toolUseId": b.data.get("id", ""),
                            "name": b.data.get("name", ""),
                            "input": b.data.get("input", {}),
                        }
                    })
            if content:
                converse_msgs.append({"role": "assistant", "content": content})

    return system, converse_msgs


def _format_tools(tools: list[ToolSchema]) -> list:
    return [
        {
            "toolSpec": {
                "name": t.name,
                "description": t.description,
                "inputSchema": {"json": t.input_schema},
            }
        }
        for t in tools
    ]


def _get_bedrock_client(region: str, role_arn: str = "", profile: str = ""):
    import boto3

    session_kwargs = {}
    if profile:
        session_kwargs["profile_name"] = profile

    session = boto3.Session(region_name=region, **session_kwargs)

    if role_arn:
        sts = session.client("sts")
        creds = sts.assume_role(
            RoleArn=role_arn, RoleSessionName="koan-agent",
        )["Credentials"]
        return boto3.client(
            "bedrock-runtime",
            region_name=region,
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        )

    return session.client("bedrock-runtime", region_name=region)


class BedrockProvider(BaseProvider):
    """AWS Bedrock provider using converse_stream for real-time streaming."""

    def __init__(
        self,
        name: str = "bedrock",
        model: str = "us.anthropic.claude-sonnet-4-20250514-v1:0",
        region: str = "us-east-1",
        role_arn: str = "",
        profile: str = "",
    ):
        self.name = name
        self._model = model
        self._region = region
        self._role_arn = role_arn
        self._profile = profile
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            self._client = _get_bedrock_client(self._region, self._role_arn, self._profile)
        return self._client

    def is_available(self) -> bool:
        try:
            self._ensure_client()
            return True
        except Exception:
            return False

    async def stream(
        self, messages: list[Message], tools: list[ToolSchema]
    ) -> AsyncIterator[Event]:
        client = self._ensure_client()
        system, converse_msgs = _format_messages(messages)

        kwargs: dict = {"modelId": self._model, "messages": converse_msgs}
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["toolConfig"] = {"tools": _format_tools(tools)}

        try:
            response = client.converse_stream(**kwargs)
        except Exception as exc:
            raise ProviderError(f"Bedrock error: {exc}") from exc

        # Track current tool use being assembled
        current_tool_id = ""
        current_tool_name = ""
        current_tool_input = ""

        for event in response.get("stream", []):

            # Text streaming — yields immediately for real-time display
            if "contentBlockDelta" in event:
                delta = event["contentBlockDelta"]["delta"]
                if "text" in delta:
                    yield Event(type=EventType.TEXT_DELTA, data={"text": delta["text"]})
                elif "toolUse" in delta:
                    # Tool input JSON arrives in fragments
                    current_tool_input += delta["toolUse"].get("input", "")

            # Block start — new text or tool_use block beginning
            elif "contentBlockStart" in event:
                start = event["contentBlockStart"].get("start", {})
                if "toolUse" in start:
                    current_tool_id = start["toolUse"].get("toolUseId", "")
                    current_tool_name = start["toolUse"].get("name", "")
                    current_tool_input = ""

            # Block stop — emit completed tool call
            elif "contentBlockStop" in event:
                if current_tool_name:
                    try:
                        parsed_input = json.loads(current_tool_input) if current_tool_input else {}
                    except json.JSONDecodeError:
                        parsed_input = {"raw": current_tool_input}

                    yield Event(type=EventType.TOOL_USE, data={
                        "id": current_tool_id,
                        "name": current_tool_name,
                        "input": parsed_input,
                    })
                    current_tool_id = ""
                    current_tool_name = ""
                    current_tool_input = ""

            # Metadata — usage stats
            elif "metadata" in event:
                usage = event["metadata"].get("usage", {})
                if usage:
                    yield Event(type=EventType.USAGE, data={
                        "input_tokens": usage.get("inputTokens", 0),
                        "output_tokens": usage.get("outputTokens", 0),
                    })

        yield Event(type=EventType.MESSAGE_STOP)
