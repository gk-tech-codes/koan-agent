"""System prompt builder.

Adapted from claw-code prompt.rs: OS info, cwd, tool descriptions, mode context.
"""

from __future__ import annotations

import os
import platform

from koan.tools.registry import ToolRegistry
from koan.types import Mode


def build_system_prompt(mode: Mode, tools: ToolRegistry) -> str:
    tool_names = ", ".join(tools.names()) if tools.names() else "(none)"

    return f"""You are Kōan, a personal AI coding agent running in the user's terminal.

Environment:
- OS: {platform.system()} {platform.machine()}
- CWD: {os.getcwd()}
- Mode: {mode.value}

Available tools: {tool_names}

When the user asks you to do something, use the available tools to accomplish it.
For file operations, use read_file, write_file, glob_search, grep_search.
For shell commands, use bash.
Always explain what you're doing before using a tool.
Be concise and direct."""
