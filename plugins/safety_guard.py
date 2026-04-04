"""Safety guard plugin — blocks dangerous commands."""

from koan.plugins.hooks import hook
from koan.types import HookResult

_BLOCKED_PATTERNS = [
    "rm -rf /",
    "rm -rf ~",
    "rm -rf *",
    "mkfs",
    "> /dev/sda",
    "dd if=/dev/zero",
    ":(){ :|:& };:",
]


@hook("before_tool")
def block_dangerous(**kwargs):
    tool_name = kwargs.get("tool_name", "")
    tool_input = kwargs.get("tool_input", {})

    if tool_name != "bash":
        return None

    command = tool_input.get("command", "")
    for pattern in _BLOCKED_PATTERNS:
        if pattern in command:
            return HookResult.deny(f"Blocked dangerous command: {pattern}")

    return None
