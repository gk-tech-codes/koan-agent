"""File tools — read_file, write_file, glob, grep.

Adapted from claw-code file_ops.rs: workspace boundary checks, size limits.
"""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path

from koan.tools.registry import tool

_MAX_READ = 256 * 1024  # 256KB


@tool(name="read_file", description="Read the contents of a file", permission="read")
def read_file(path: str, start_line: int = 1, end_line: int = -1) -> str:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    if p.stat().st_size > _MAX_READ:
        raise ValueError(f"File too large: {p.stat().st_size} bytes (max {_MAX_READ})")

    lines = p.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    start = max(0, start_line - 1)
    end = end_line if end_line > 0 else len(lines)
    selected = lines[start:end]

    numbered = [f"{start + i + 1:>5}│ {line}" for i, line in enumerate(selected)]
    return "".join(numbered)


@tool(name="write_file", description="Write content to a file", permission="write")
def write_file(path: str, content: str) -> str:
    p = Path(path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} bytes to {path}"


@tool(name="glob_search", description="Find files matching a glob pattern", permission="read")
def glob_search(pattern: str, path: str = ".") -> str:
    root = Path(path).expanduser().resolve()
    matches = sorted(str(m.relative_to(root)) for m in root.rglob(pattern))[:100]
    if not matches:
        return f"No files matching '{pattern}'"
    return "\n".join(matches)


@tool(name="grep_search", description="Search file contents with regex", permission="read")
def grep_search(pattern: str, path: str = ".", include: str = "") -> str:
    root = Path(path).expanduser().resolve()
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return f"Invalid regex: {e}"

    results = []
    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            if include and not fnmatch.fnmatch(fname, include):
                continue
            fpath = Path(dirpath) / fname
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeDecodeError):
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    rel = fpath.relative_to(root)
                    results.append(f"{rel}:{i}: {line.rstrip()}")
                    if len(results) >= 50:
                        return "\n".join(results) + "\n[truncated at 50 matches]"
    return "\n".join(results) if results else f"No matches for '{pattern}'"
