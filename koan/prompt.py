"""System prompt builder.

Adapted from claw-code prompt.rs: OS info, cwd, tool descriptions, mode context.
Injects recalled memories when in memory mode.
"""

from __future__ import annotations

import os
import platform

from koan.tools.registry import ToolRegistry
from koan.types import Mode


def build_system_prompt(mode: Mode, tools: ToolRegistry, memory_context: str = "") -> str:
    tool_list = "\n".join(
        f"  - {s.name}: {s.description}" for s in tools.schemas()
    ) if tools.schemas() else "  (none)"

    memory_section = ""
    if memory_context:
        memory_section = f"\n{memory_context}\n"

    return f"""You are Kōan, a personal AI coding agent running in the user's terminal.

Environment:
- OS: {platform.system()} {platform.machine()}
- Working directory: {os.getcwd()}
- Mode: {mode.value}
{memory_section}
Available tools:
{tool_list}

Guidelines:
- Answer questions directly and conversationally. Only use tools when the task requires interacting with the filesystem, running commands, or fetching external data.
- Do NOT use tools for simple questions, math, explanations, or general knowledge.
- When you do use tools, briefly explain what you're doing and why.
- Keep responses concise and well-formatted.
- Use markdown formatting for readability when appropriate.
- If you have memory tools available, use memory_store to save important user preferences or facts you learn during the conversation."""
