"""Session compaction — summarize older messages to keep context manageable.

Adapted from claw-code compact.rs: when cumulative tokens exceed threshold,
older messages are summarized into a compact system message, preserving
only the most recent messages verbatim.
"""

from __future__ import annotations

from koan.log import get_logger
from koan.types import ContentBlock, Message, MessageRole

log = get_logger("compact")

DEFAULT_PRESERVE_RECENT = 4
DEFAULT_COMPACT_THRESHOLD = 80000  # tokens


def estimate_tokens(messages: list[Message]) -> int:
    """Rough token estimate: ~4 chars per token."""
    total = 0
    for m in messages:
        for b in m.blocks:
            text = b.data.get("text", "") or b.data.get("output", "")
            total += len(str(text)) // 4
    return total


def should_compact(messages: list[Message], threshold: int = DEFAULT_COMPACT_THRESHOLD) -> bool:
    """Check if messages exceed the compaction threshold."""
    return estimate_tokens(messages) >= threshold


def _summarize_messages(messages: list[Message]) -> str:
    """Summarize a list of messages into a compact description."""
    user_count = sum(1 for m in messages if m.role == MessageRole.USER)
    assistant_count = sum(1 for m in messages if m.role == MessageRole.ASSISTANT)

    # Collect tool names used
    tool_names = []
    for m in messages:
        for b in m.blocks:
            if b.type == "tool_use":
                name = b.data.get("name", "")
                if name and name not in tool_names:
                    tool_names.append(name)

    # Collect recent user requests
    user_requests = []
    for m in messages:
        if m.role == MessageRole.USER:
            for b in m.blocks:
                if b.type == "text":
                    text = b.data.get("text", "").strip()
                    if text and len(text) > 5:
                        user_requests.append(text[:150])

    # Collect file paths touched
    files = []
    for m in messages:
        for b in m.blocks:
            if b.type == "tool_use":
                path = b.data.get("input", {}).get("path", "")
                if path and path not in files:
                    files.append(path)
            if b.type == "tool_result":
                output = b.data.get("output", "")
                if "Wrote" in output and "bytes to" in output:
                    parts = output.split("bytes to ")
                    if len(parts) > 1:
                        fp = parts[1].strip()
                        if fp and fp not in files:
                            files.append(fp)

    lines = [
        "Summary of earlier conversation:",
        f"- {len(messages)} messages compacted (user={user_count}, assistant={assistant_count}).",
    ]
    if tool_names:
        lines.append(f"- Tools used: {', '.join(tool_names)}.")
    if files:
        lines.append(f"- Files touched: {', '.join(files[:10])}.")
    if user_requests:
        lines.append("- Recent user requests:")
        for req in user_requests[-3:]:
            lines.append(f"  - {req}")

    return "\n".join(lines)


def compact_messages(
    messages: list[Message],
    preserve_recent: int = DEFAULT_PRESERVE_RECENT,
) -> tuple[list[Message], int]:
    """Compact older messages into a summary, keeping recent ones.

    Returns (compacted_messages, removed_count).
    """
    if len(messages) <= preserve_recent:
        return messages, 0

    keep_from = len(messages) - preserve_recent
    removed = messages[:keep_from]
    preserved = messages[keep_from:]

    summary_text = _summarize_messages(removed)

    log.info("Compacting: %d messages removed, %d preserved, ~%d tokens freed",
             len(removed), len(preserved), estimate_tokens(removed))

    summary_msg = Message(
        role=MessageRole.USER,
        blocks=[ContentBlock(
            type="text",
            data={"text": f"[Previous conversation summary]\n{summary_text}\n\nRecent messages are preserved below. Continue from where we left off."},
        )],
    )

    return [summary_msg] + preserved, len(removed)
