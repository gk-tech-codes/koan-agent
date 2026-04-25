"""Explain reasoning — shows which memories influenced the agent's decisions.

Enabled with --explain flag. After each response, shows what memories
were recalled and how they influenced the output.
"""

from __future__ import annotations

import time
from typing import Any

from koan.log import get_logger

log = get_logger("explain")


class ExplainTracker:
    """Tracks which memories and context influenced the response."""

    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self._recalled_memories: list[dict] = []
        self._recalled_episodes: list[str] = []
        self._matched_playbooks: list[str] = []
        self._tools_used: list[str] = []

    def reset(self):
        self._recalled_memories = []
        self._recalled_episodes = []
        self._matched_playbooks = []
        self._tools_used = []

    def record_memory(self, mem_type: str, content: str):
        if self.enabled:
            self._recalled_memories.append({"type": mem_type, "content": content[:80]})

    def record_episode(self, summary: str):
        if self.enabled:
            self._recalled_episodes.append(summary[:80])

    def record_playbook(self, name: str):
        if self.enabled:
            self._matched_playbooks.append(name)

    def record_tool(self, name: str):
        if self.enabled:
            self._tools_used.append(name)

    def format_explanation(self) -> str:
        """Format the reasoning explanation for display."""
        if not self.enabled:
            return ""

        parts = []
        if self._recalled_memories:
            parts.append("\033[90m◇ Reasoning:\033[0m")
            for m in self._recalled_memories:
                parts.append(f"\033[90m  ← [{m['type']}] {m['content']}\033[0m")
        if self._recalled_episodes:
            for e in self._recalled_episodes:
                parts.append(f"\033[90m  ← [episode] {e}\033[0m")
        if self._matched_playbooks:
            for p in self._matched_playbooks:
                parts.append(f"\033[90m  ← [playbook] {p}\033[0m")
        if self._tools_used:
            parts.append(f"\033[90m  tools: {' → '.join(self._tools_used)}\033[0m")

        return "\n".join(parts)


# Global instance
explain_tracker = ExplainTracker(enabled=False)
