"""Diff preview — shows what changed before/after file writes.

Used by the tool output renderer to show colored diffs
instead of raw "Wrote X bytes" messages.
"""

from __future__ import annotations

from pathlib import Path


def compute_diff(path: str, new_content: str = None, old_content: str = None) -> str:
    """Compute a colored diff summary for a file change."""
    p = Path(path).expanduser().resolve()

    if old_content is None:
        if p.is_file():
            try:
                old_content = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                old_content = ""
        else:
            old_content = ""

    if new_content is None:
        return ""

    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()

    if not old_lines:
        # New file
        added = len(new_lines)
        preview = new_lines[:8]
        lines = [f"\033[90m  ┌─ new file ({added} lines) ──────────────\033[0m"]
        for l in preview:
            lines.append(f"\033[90m  │\033[0m \033[32m+ {l[:70]}\033[0m")
        if added > 8:
            lines.append(f"\033[90m  │ ... +{added - 8} more lines\033[0m")
        lines.append(f"\033[90m  └──────────────────────────────────────\033[0m")
        return "\n".join(lines)

    # Compute simple diff
    added = 0
    removed = 0
    changed_lines = []

    import difflib
    diff = list(difflib.unified_diff(old_lines, new_lines, lineterm="", n=0))

    for line in diff:
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
            if len(changed_lines) < 6:
                changed_lines.append(f"\033[32m+ {line[1:][:70]}\033[0m")
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
            if len(changed_lines) < 6:
                changed_lines.append(f"\033[31m- {line[1:][:70]}\033[0m")

    if not changed_lines:
        return "\033[90m  (no changes)\033[0m"

    summary = f"+{added} -{removed} lines"
    lines = [f"\033[90m  ┌─ diff ({summary}) ──────────────────\033[0m"]
    for cl in changed_lines:
        lines.append(f"\033[90m  │\033[0m {cl}")
    remaining = (added + removed) - len(changed_lines)
    if remaining > 0:
        lines.append(f"\033[90m  │ ... {remaining} more changes\033[0m")
    lines.append(f"\033[90m  └──────────────────────────────────────\033[0m")
    return "\n".join(lines)


def format_bash_result(command: str, output: str, is_error: bool) -> str:
    """Format bash tool result compactly."""
    cmd_short = command[:60] + ("..." if len(command) > 60 else "")

    if is_error:
        first_line = output.split("\n")[0][:80]
        return f"\033[31m✗\033[0m \033[36mbash\033[0m: \033[90m{cmd_short}\033[0m → \033[31m{first_line}\033[0m"

    # Parse common outputs
    if "passed" in output.lower() and ("failed" in output.lower() or "error" in output.lower()):
        return f"\033[32m✓\033[0m \033[36mbash\033[0m: \033[90m{cmd_short}\033[0m → {output.strip()[:80]}"

    lines = output.strip().split("\n")
    if len(lines) == 1 and len(lines[0]) < 80:
        return f"\033[32m✓\033[0m \033[36mbash\033[0m: \033[90m{cmd_short}\033[0m → {lines[0]}"

    return f"\033[32m✓\033[0m \033[36mbash\033[0m: \033[90m{cmd_short}\033[0m ({len(lines)} lines)"


def format_file_result(tool_name: str, path: str, output: str, diff: str = "") -> str:
    """Format file tool result with optional diff."""
    fname = Path(path).name if path else "?"

    if tool_name == "read_file":
        lines = output.count("\n") + 1
        return f"\033[32m✓\033[0m \033[36mread\033[0m \033[97m{fname}\033[0m \033[90m({lines} lines)\033[0m"

    if tool_name == "write_file":
        result = f"\033[32m✓\033[0m \033[36mwrite\033[0m \033[97m{fname}\033[0m"
        if diff:
            return result + "\n" + diff
        return result

    if tool_name == "edit_file":
        result = f"\033[32m✓\033[0m \033[36medit\033[0m \033[97m{fname}\033[0m"
        if diff:
            return result + "\n" + diff
        return result

    if tool_name == "glob_search":
        count = len(output.strip().split("\n")) if output.strip() else 0
        return f"\033[32m✓\033[0m \033[36mglob\033[0m \033[90m{count} files found\033[0m"

    if tool_name == "grep_search":
        count = len(output.strip().split("\n")) if output.strip() else 0
        return f"\033[32m✓\033[0m \033[36mgrep\033[0m \033[90m{count} matches\033[0m"

    return f"\033[32m✓\033[0m \033[36m{tool_name}\033[0m"
