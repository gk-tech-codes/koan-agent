"""Output rendering — colored, structured terminal output.

Handles raw LLM output and renders it cleanly with colors.
"""

from __future__ import annotations

import re
import sys


# ── Colors ───────────────────────────────────────────────────

class C:
    """ANSI color codes."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[90m"
    # Text
    WHITE = "\033[97m"
    GRAY = "\033[90m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    # Backgrounds
    BG_DARK = "\033[48;5;236m"


class Renderer:
    """Cleans and renders streamed text to the terminal with colors."""

    def __init__(self):
        self._col = 0
        self._line_start = True
        self._in_code_block = False
        self._code_lang = ""

    def write(self, text: str) -> None:
        """Write text to stdout with markdown-aware coloring."""
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        i = 0
        while i < len(text):
            # Detect code block boundaries
            if text[i:i+3] == "```":
                if not self._in_code_block:
                    # Opening code block
                    self._in_code_block = True
                    end = text.find("\n", i)
                    if end == -1:
                        self._code_lang = text[i+3:].strip()
                        i = len(text)
                    else:
                        self._code_lang = text[i+3:end].strip()
                        i = end + 1
                    lang_label = f" {self._code_lang}" if self._code_lang else ""
                    sys.stdout.write(f"\n{C.DIM}┌──{lang_label}{'─' * max(0, 40 - len(lang_label))}{C.RESET}\n")
                    self._col = 0
                    self._line_start = True
                    continue
                else:
                    # Closing code block
                    self._in_code_block = False
                    self._code_lang = ""
                    i += 3
                    sys.stdout.write(f"\n{C.DIM}└{'─' * 42}{C.RESET}\n")
                    self._col = 0
                    self._line_start = True
                    continue

            ch = text[i]

            if ch == "\n":
                sys.stdout.write("\n")
                self._col = 0
                self._line_start = True
                if self._in_code_block:
                    sys.stdout.write(f"{C.DIM}│{C.RESET} {C.CYAN}")
            else:
                if self._line_start and not self._in_code_block:
                    self._line_start = False
                    # Color markdown headers
                    rest = text[i:]
                    if rest.startswith("## "):
                        sys.stdout.write(f"{C.BOLD}{C.BLUE}")
                    elif rest.startswith("# "):
                        sys.stdout.write(f"{C.BOLD}{C.MAGENTA}")
                    elif rest.startswith("### "):
                        sys.stdout.write(f"{C.BOLD}{C.CYAN}")
                    elif rest.startswith("- ") or rest.startswith("* "):
                        sys.stdout.write(f"{C.GREEN}•{C.RESET} ")
                        i += 2
                        continue
                    elif re.match(r"^\d+\. ", rest):
                        m = re.match(r"^(\d+)\. ", rest)
                        sys.stdout.write(f"{C.YELLOW}{m.group(1)}.{C.RESET} ")
                        i += len(m.group(0))
                        continue

                if self._in_code_block:
                    if self._line_start:
                        sys.stdout.write(f"{C.DIM}│{C.RESET} {C.CYAN}")
                        self._line_start = False
                    sys.stdout.write(ch)
                else:
                    # Inline formatting
                    rest = text[i:]
                    # Bold **text**
                    bold_match = re.match(r"\*\*(.+?)\*\*", rest)
                    if bold_match:
                        sys.stdout.write(f"{C.BOLD}{C.WHITE}{bold_match.group(1)}{C.RESET}")
                        i += len(bold_match.group(0))
                        continue
                    # Inline code `text`
                    code_match = re.match(r"`([^`]+)`", rest)
                    if code_match:
                        sys.stdout.write(f"{C.CYAN}{code_match.group(1)}{C.RESET}")
                        i += len(code_match.group(0))
                        continue
                    # Reset color at end of header lines
                    sys.stdout.write(ch)

                self._col += 1

            i += 1

        # Reset at end of each write
        if not self._in_code_block:
            sys.stdout.write(C.RESET)
        sys.stdout.flush()

    def tool_result(self, name: str, output: str, is_error: bool) -> None:
        """Render a tool result summary."""
        if is_error:
            icon = f"{C.RED}✗{C.RESET}"
        else:
            icon = f"{C.GREEN}✓{C.RESET}"
        preview = output[:120].replace("\n", " ").replace("\r", "")
        if len(output) > 120:
            preview += "…"
        sys.stdout.write(f"\n  {icon} {C.CYAN}{name}{C.RESET}: {C.DIM}{preview}{C.RESET}\n")
        sys.stdout.flush()

    def newline(self) -> None:
        if not self._line_start:
            sys.stdout.write(C.RESET + "\n")
            sys.stdout.flush()
            self._col = 0
            self._line_start = True

    def banner(self, text: str) -> None:
        """Print a styled banner."""
        sys.stdout.write(f"{C.DIM}{'─' * 44}{C.RESET}\n")
        sys.stdout.write(f"{C.BOLD}{text}{C.RESET}\n")
        sys.stdout.write(f"{C.DIM}{'─' * 44}{C.RESET}\n")
        sys.stdout.flush()
