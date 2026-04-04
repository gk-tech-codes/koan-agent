"""Core conversation loop — the heart of Kōan.

Adapted from claw-code conversation.rs: run_turn() loop with
tool execution, permission checks, and session persistence.
"""

from __future__ import annotations

from typing import Any, Callable

from koan.errors import ProviderError
from koan.session import Session
from koan.spinner import Spinner
from koan.tools.registry import ToolRegistry
from koan.types import (
    ContentBlock,
    Decision,
    Event,
    EventType,
    Message,
    MessageRole,
    TokenUsage,
    ToolUse,
)


async def run_turn(
    user_text: str,
    session: Session,
    provider: Any,
    tools: ToolRegistry,
    system_prompt: str,
    max_iterations: int = 25,
    permission_check: Callable | None = None,
    on_text: Callable[[str], None] | None = None,
) -> Message:
    """Run one user turn through the conversation loop."""

    session.push_user_text(user_text)

    sys_msg = Message(
        role=MessageRole.SYSTEM,
        blocks=[ContentBlock(type="text", data={"text": system_prompt})],
    )

    iteration = 0
    last_assistant_msg = None

    while iteration < max_iterations:
        iteration += 1
        all_messages = [sys_msg] + session.messages

        spinner = Spinner("thinking")
        spinner.start()

        text_parts: list[str] = []
        tool_uses: list[ToolUse] = []
        usage = None
        first_token = True

        try:
            async for event in provider.stream(all_messages, tools.schemas()):
                if event.type == EventType.TEXT_DELTA:
                    if first_token:
                        spinner.stop()
                        first_token = False
                    text = event.data.get("text", "")
                    text_parts.append(text)
                    if on_text:
                        on_text(text)

                elif event.type == EventType.TOOL_USE:
                    if first_token:
                        spinner.stop()
                        first_token = False
                    tool_uses.append(ToolUse(
                        id=event.data.get("id", ""),
                        name=event.data.get("name", ""),
                        input=event.data.get("input", {}),
                    ))

                elif event.type == EventType.USAGE:
                    usage = TokenUsage(
                        input_tokens=event.data.get("input_tokens", 0),
                        output_tokens=event.data.get("output_tokens", 0),
                    )

        except ProviderError:
            spinner.stop()
            raise

        if first_token:
            spinner.stop()

        # Build assistant message
        blocks: list[ContentBlock] = []
        full_text = "".join(text_parts)
        if full_text:
            blocks.append(ContentBlock(type="text", data={"text": full_text}))
        for tu in tool_uses:
            blocks.append(ContentBlock(
                type="tool_use",
                data={"id": tu.id, "name": tu.name, "input": tu.input},
            ))

        if blocks:
            assistant_msg = Message(role=MessageRole.ASSISTANT, blocks=blocks, usage=usage)
            session.push_message(assistant_msg)
            last_assistant_msg = assistant_msg

        if not tool_uses:
            break

        # Execute each tool call
        result_blocks: list[ContentBlock] = []
        for tu in tool_uses:
            if permission_check:
                decision = permission_check(tu.name, tu.input)
                if decision == Decision.DENY:
                    result_blocks.append(ContentBlock(
                        type="tool_result",
                        data={
                            "tool_use_id": tu.id,
                            "output": f"Permission denied: {tu.name}",
                            "is_error": True,
                        },
                    ))
                    continue

            tool_spinner = Spinner(f"{tu.name}", tool=True)
            tool_spinner.start()

            result = await tools.execute(tu.name, tu.input)
            result.tool_use_id = tu.id

            tool_spinner.stop()

            result_blocks.append(ContentBlock(
                type="tool_result",
                data={
                    "tool_use_id": tu.id,
                    "output": result.output,
                    "is_error": result.is_error,
                },
            ))

            status = "✗" if result.is_error else "✓"
            preview = result.output[:100].replace("\n", " ")
            if on_text:
                on_text(f"\n  {status} {tu.name}: {preview}\n")

        if result_blocks:
            tool_result_msg = Message(role=MessageRole.USER, blocks=result_blocks)
            session.push_message(tool_result_msg)

    return last_assistant_msg
