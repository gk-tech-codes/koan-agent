"""Episodic memory — compressed session summaries.

Stores what happened in past sessions: goal, tools used, files touched,
outcome, errors, and a short summary. Enables "last time you did X..." recall.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from koan.types import _iso_now


def _extract_user_goal(messages: list[dict]) -> str:
    """Extract the user's goal from the first user message."""
    for m in messages:
        if m.get("role") == "user":
            for b in m.get("blocks", []):
                if b.get("type") == "text":
                    text = b.get("data", {}).get("text", "").strip()
                    if text:
                        return text[:200]
    return "unknown"


def _extract_tools_used(messages: list[dict]) -> list[str]:
    """Extract unique tool names used in the session."""
    tools = []
    for m in messages:
        if m.get("role") == "assistant":
            for b in m.get("blocks", []):
                if b.get("type") == "tool_use":
                    name = b.get("data", {}).get("name", "")
                    if name and name not in tools:
                        tools.append(name)
    return tools


def _extract_files_touched(messages: list[dict]) -> list[str]:
    """Extract file paths from tool calls."""
    files = []
    for m in messages:
        for b in m.get("blocks", []):
            data = b.get("data", {})
            # From tool_use inputs
            if b.get("type") == "tool_use":
                inp = data.get("input", {})
                path = inp.get("path", "")
                if path and path not in files:
                    files.append(path)
            # From tool_result outputs mentioning file writes
            if b.get("type") == "tool_result":
                output = data.get("output", "")
                if "Wrote" in output and "bytes to" in output:
                    parts = output.split("bytes to ")
                    if len(parts) > 1:
                        fp = parts[1].strip()
                        if fp and fp not in files:
                            files.append(fp)
    return files


def _detect_errors(messages: list[dict]) -> list[str]:
    """Extract error messages from tool results."""
    errors = []
    for m in messages:
        for b in m.get("blocks", []):
            if b.get("type") == "tool_result":
                data = b.get("data", {})
                if data.get("is_error"):
                    err = data.get("output", "")[:150]
                    if err and err not in errors:
                        errors.append(err)
    return errors


def _detect_outcome(messages: list[dict]) -> str:
    """Detect if the session ended successfully."""
    errors = _detect_errors(messages)
    tools = _extract_tools_used(messages)
    if not tools:
        return "chat_only"
    if errors and len(errors) > len(tools):
        return "failed"
    if errors:
        return "partial"
    return "success"


def _build_summary(goal: str, tools: list[str], files: list[str],
                   outcome: str, errors: list[str]) -> str:
    """Build a human-readable session summary."""
    parts = [f"Goal: {goal}."]
    if tools:
        parts.append(f"Used: {', '.join(tools)}.")
    if files:
        parts.append(f"Files: {', '.join(files[:5])}.")
    if errors:
        parts.append(f"Errors: {errors[0]}.")
    parts.append(f"Outcome: {outcome}.")
    return " ".join(parts)


class Episode:
    """A single session episode."""

    def __init__(self, data: dict):
        self.id: str = data.get("id", "")
        self.session_id: str = data.get("session_id", "")
        self.goal: str = data.get("goal", "")
        self.tools_used: list[str] = data.get("tools_used", [])
        self.files_touched: list[str] = data.get("files_touched", [])
        self.outcome: str = data.get("outcome", "")
        self.errors: list[str] = data.get("errors", [])
        self.summary: str = data.get("summary", "")
        self.created_at: str = data.get("created_at", "")
        self.message_count: int = data.get("message_count", 0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "goal": self.goal,
            "tools_used": self.tools_used,
            "files_touched": self.files_touched,
            "outcome": self.outcome,
            "errors": self.errors,
            "summary": self.summary,
            "created_at": self.created_at,
            "message_count": self.message_count,
        }


class EpisodicStore:
    """JSONL-backed store for session episodes."""

    def __init__(self, memory_dir: Path):
        self._dir = memory_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "episodes.jsonl"
        self._episodes: list[Episode] = []
        self._load()

    def _load(self):
        if not self._path.is_file():
            return
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    self._episodes.append(Episode(json.loads(line)))
                except (json.JSONDecodeError, KeyError):
                    continue

    def _save(self):
        with open(self._path, "w", encoding="utf-8") as f:
            for ep in self._episodes:
                f.write(json.dumps(ep.to_dict(), ensure_ascii=False) + "\n")

    def store(self, episode: Episode) -> None:
        self._episodes.append(episode)
        self._save()

    def all(self) -> list[Episode]:
        return list(self._episodes)

    def count(self) -> int:
        return len(self._episodes)

    def recent(self, limit: int = 5) -> list[Episode]:
        return self._episodes[-limit:]

    def search(self, query: str) -> list[Episode]:
        terms = query.lower().split()
        results = []
        for ep in self._episodes:
            text = (ep.goal + " " + ep.summary + " " + " ".join(ep.tools_used)
                    + " " + " ".join(ep.files_touched)).lower()
            if all(t in text for t in terms):
                results.append(ep)
        return results


def extract_episode(session_path: Path) -> Episode | None:
    """Extract an episode from a completed session JSONL file."""
    if not session_path.is_file():
        return None

    messages = []
    with open(session_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not messages:
        return None

    goal = _extract_user_goal(messages)
    tools = _extract_tools_used(messages)
    files = _extract_files_touched(messages)
    errors = _detect_errors(messages)
    outcome = _detect_outcome(messages)
    summary = _build_summary(goal, tools, files, outcome, errors)

    return Episode({
        "id": f"ep_{session_path.stem}",
        "session_id": session_path.stem,
        "goal": goal,
        "tools_used": tools,
        "files_touched": files,
        "outcome": outcome,
        "errors": errors,
        "summary": summary,
        "created_at": _iso_now(),
        "message_count": len(messages),
    })


def format_episodes_for_prompt(episodes: list[Episode]) -> str:
    """Format recent episodes as context for the system prompt."""
    if not episodes:
        return ""
    lines = ["Recent session history:"]
    for ep in episodes:
        lines.append(f"  - {ep.summary}")
    return "\n".join(lines)
