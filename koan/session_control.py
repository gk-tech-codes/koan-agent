"""Session control — list, resume, and export sessions."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def cleanup_old_sessions(session_dir: Path, keep_days: int = 30) -> int:
    """Delete session files older than keep_days. Returns count deleted."""
    import time
    cutoff = time.time() - (keep_days * 86400)
    deleted = 0
    session_dir.mkdir(parents=True, exist_ok=True)
    for f in session_dir.glob("*.jsonl"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            deleted += 1
    return deleted


def list_sessions(session_dir: Path, limit: int = 20) -> list[dict]:
    """List recent sessions with metadata."""
    session_dir.mkdir(parents=True, exist_ok=True)
    sessions = []

    for f in sorted(session_dir.glob("*.jsonl"), reverse=True)[:limit]:
        msg_count = 0
        first_user_msg = ""
        total_tokens = 0

        try:
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    msg_count += 1
                    # Get first user message as summary
                    if not first_user_msg and record.get("role") == "user":
                        for b in record.get("blocks", []):
                            if b.get("type") == "text":
                                first_user_msg = b.get("data", {}).get("text", "")[:80]
                                break
                    # Sum tokens
                    usage = record.get("usage", {})
                    total_tokens += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        except (json.JSONDecodeError, OSError):
            continue

        sessions.append({
            "id": f.stem,
            "path": str(f),
            "messages": msg_count,
            "tokens": total_tokens,
            "summary": first_user_msg or "(empty)",
            "size_kb": round(f.stat().st_size / 1024, 1),
        })

    return sessions


def format_session_list(sessions: list[dict]) -> str:
    """Format session list for display."""
    if not sessions:
        return "No sessions found."

    lines = [f"Sessions ({len(sessions)}):\n"]
    for s in sessions:
        lines.append(
            f"  \033[36m{s['id']}\033[0m  "
            f"{s['messages']} msgs | {s['tokens']} tokens | {s['size_kb']}KB"
        )
        lines.append(f"    {s['summary']}")
    return "\n".join(lines)


def export_session(session_path: Path) -> str:
    """Export a session as readable text."""
    if not session_path.is_file():
        return f"Session not found: {session_path}"

    lines = [f"# Session: {session_path.stem}\n"]

    with open(session_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            role = record.get("role", "?")
            blocks = record.get("blocks", [])

            for b in blocks:
                btype = b.get("type", "")
                data = b.get("data", {})

                if btype == "text":
                    text = data.get("text", "")
                    lines.append(f"**{role}**: {text}\n")
                elif btype == "tool_use":
                    name = data.get("name", "")
                    inp = json.dumps(data.get("input", {}))[:200]
                    lines.append(f"**{role}** → `{name}({inp})`\n")
                elif btype == "tool_result":
                    output = data.get("output", "")[:200]
                    err = " (ERROR)" if data.get("is_error") else ""
                    lines.append(f"**tool_result**{err}: {output}\n")

    return "\n".join(lines)
