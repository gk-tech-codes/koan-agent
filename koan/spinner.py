"""Kōan spinner — the trademark thinking indicator.

The Kōan symbol: a rotating zen circle (ensō) that pulses while thinking.
"""

from __future__ import annotations

import sys
import threading
import time

# The Kōan signature spinner — zen-inspired
_FRAMES = ["◜", "◠", "◝", "◞", "◡", "◟"]
_TOOL_FRAMES = ["⟡", "⬡", "⟡", "⬢"]
_THINKING_PREFIX = "\033[90m"  # dim gray
_RESET = "\033[0m"


class Spinner:
    """Animated spinner shown while waiting for LLM or tool execution."""

    def __init__(self, label: str = "thinking", tool: bool = False):
        self._label = label
        self._frames = _TOOL_FRAMES if tool else _FRAMES
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
        # Clear the spinner line
        sys.stderr.write(f"\r\033[K")
        sys.stderr.flush()

    def update(self, label: str):
        self._label = label

    def _spin(self):
        i = 0
        while self._running:
            frame = self._frames[i % len(self._frames)]
            sys.stderr.write(f"\r{_THINKING_PREFIX}{frame} {self._label}...{_RESET}")
            sys.stderr.flush()
            i += 1
            time.sleep(0.12)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()
