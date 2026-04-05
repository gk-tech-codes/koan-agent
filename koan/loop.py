"""Core conversation loop — the heart of Kōan.

Adapted from claw-code conversation.rs: run_turn() loop with
tool execution, permission checks, and session persistence.
"""

from __future__ import annotations

from typing import Any, Callable

from koan.compact import compact_messages, estimate_tokens, should_compact
from koan.errors import ProviderError
from koan.log import get_logger
from koan.plugins.hooks import dispatch as dispatch_hook

log = get_logger("loop")
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
    log.debug("Turn started: %s", user_text[:100])

    sys_msg = Message(
        role=MessageRole.SYSTEM,
        blocks=[ContentBlock(type="text", data={"text": system_prompt})],
    )

    iteration = 0
    last_assistant_msg = None

    while iteration < max_iterations:
        iteration += 1

        # Auto-compact if context is getting too large (claw-code pattern)
        if should_compact(session.messages):
            compacted, removed = compact_messages(session.messages)
            session.messages = compacted
            log.info("Auto-compacted: removed %d messages", removed)

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
            log.error("Provider error on iteration %d", iteration)
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
            # Dispatch on_turn_end with usage info
            usage_data = {}
            if usage:
                usage_data = {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}
                log.debug("Turn complete: %d input, %d output tokens", usage.input_tokens, usage.output_tokens)
            await dispatch_hook("on_turn_end", usage=usage_data)
            break

        log.debug("Executing %d tool call(s): %s", len(tool_uses), [t.name for t in tool_uses])

        # Execute each tool call
        result_blocks: list[ContentBlock] = []
        total_tools = len(tool_uses)
        for tool_idx, tu in enumerate(tool_uses, 1):
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

            # Run before_tool hooks
            hook_result = await dispatch_hook(
                "before_tool", tool_name=tu.name, tool_input=tu.input
            )
            if hook_result.denied:
                result_blocks.append(ContentBlock(
                    type="tool_result",
                    data={
                        "tool_use_id": tu.id,
                        "output": f"Blocked by plugin: {hook_result.messages[0] if hook_result.messages else 'denied'}",
                        "is_error": True,
                    },
                ))
                continue
            # Apply input modifications from hooks
            effective_input = hook_result.updated_input if hook_result.updated_input else tu.input

            label = f"{tu.name} ({tool_idx}/{total_tools})" if total_tools > 1 else tu.name
            tool_spinner = Spinner(label, tool=True)
            tool_spinner.start()

            result = await tools.execute(tu.name, effective_input)
            result.tool_use_id = tu.id

            tool_spinner.stop()

            # Run after_tool hooks
            await dispatch_hook(
                "after_tool", tool_name=tu.name, tool_input=effective_input,
                output=result.output, is_error=result.is_error,
            )

            log.debug("Tool %s: %s (error=%s, len=%d)", tu.name, result.output[:80], result.is_error, len(result.output))

            # Truncate large tool outputs to prevent context bloat
            output = result.output
            if len(output) > 10000:
                output = output[:10000] + f"\n[truncated — {len(result.output)} chars total]"
                log.warning("Tool %s output truncated from %d to 10000 chars", tu.name, len(result.output))

            result_blocks.append(ContentBlock(
                type="tool_result",
                data={
                    "tool_use_id": tu.id,
                    "output": output,
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
            # Show continuation indicator — agent is about to think again
            if on_text:
                on_text("\n")

    return last_assistant_msg
