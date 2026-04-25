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

            # Show context usage indicator
            from koan.compact import estimate_tokens, DEFAULT_COMPACT_THRESHOLD
            est = estimate_tokens(session.messages)
            pct = min(100, int(est / DEFAULT_COMPACT_THRESHOLD * 100))
            if pct >= 60 and on_text:
                color = "\033[33m" if pct < 80 else "\033[31m"  # yellow or red
                on_text(f"\n{color}◈ Context: {pct}% ({est:,} / {DEFAULT_COMPACT_THRESHOLD:,} tokens)\033[0m")
                if pct >= 80:
                    on_text(f"\n\033[90m  Auto-compaction will trigger soon to free context.\033[0m")

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
            if on_text:
                from koan.diff import format_bash_result, format_file_result, compute_diff
                if tu.name == "bash":
                    cmd = effective_input.get("command", "")
                    formatted = format_bash_result(cmd, result.output, result.is_error)
                    on_text(f"\n  {formatted}\n")
                elif tu.name in ("write_file", "edit_file"):
                    path = effective_input.get("path", "")
                    content = effective_input.get("content", "")
                    new_str = effective_input.get("new_str", "")
                    # For write_file, diff is new file preview; for edit_file, show the change
                    if tu.name == "write_file" and content:
                        from koan.diff import compute_diff
                        diff = compute_diff(path, content, old_content="")
                    elif tu.name == "edit_file":
                        old = effective_input.get("old_str", "")
                        diff = f"\033[90m  ┌─ edit ──────────────────────────────\033[0m\n\033[90m  │\033[0m \033[31m- {old[:70]}\033[0m\n\033[90m  │\033[0m \033[32m+ {new_str[:70]}\033[0m\n\033[90m  └──────────────────────────────────────\033[0m" if old else ""
                    else:
                        diff = ""
                    formatted = format_file_result(tu.name, path, result.output, diff)
                    on_text(f"\n  {formatted}\n")
                elif tu.name in ("read_file", "glob_search", "grep_search"):
                    path = effective_input.get("path", effective_input.get("pattern", ""))
                    formatted = format_file_result(tu.name, path, result.output)
                    on_text(f"\n  {formatted}\n")
                else:
                    preview = result.output[:100].replace("\n", " ")
                    on_text(f"\n  {status} \033[36m{tu.name}\033[0m: {preview}\n")

        if result_blocks:
            tool_result_msg = Message(role=MessageRole.USER, blocks=result_blocks)
            session.push_message(tool_result_msg)
            # Show continuation indicator — agent is about to think again
            if on_text:
                on_text("\n")

    return last_assistant_msg
