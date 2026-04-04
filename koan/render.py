"""Output rendering — clean terminal output for streamed text.

Handles raw LLM output and renders it cleanly to the terminal.
"""

from __future__ import annotations

import sys


class Renderer:
    """Cleans and renders streamed text to the terminal."""

    def __init__(self):
        self._col = 0  # current column position
        self._line_start = True

    def write(self, text: str) -> None:
        """Write text to stdout, cleaning up formatting issues."""
        # Replace carriage returns that cause column jumping
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        for ch in text:
            if ch == "\n":
                sys.stdout.write("\n")
                self._col = 0
                self._line_start = True
            else:
                if self._line_start:
                    self._line_start = False
                sys.stdout.write(ch)
                self._col += 1

        sys.stdout.flush()

    def tool_result(self, name: str, output: str, is_error: bool) -> None:
        """Render a tool result summary."""
        status = "\033[31m✗\033[0m" if is_error else "\033[32m✓\033[0m"
        preview = output[:120].replace("\n", " ").replace("\r", "")
        if len(output) > 120:
            preview += "…"
        sys.stdout.write(f"\n  {status} \033[36m{name}\033[0m: {preview}\n")
        sys.stdout.flush()

    def newline(self) -> None:
        if not self._line_start:
            sys.stdout.write("\n")
            sys.stdout.flush()
            self._col = 0
            self._line_start = True
