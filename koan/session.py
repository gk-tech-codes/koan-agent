"""JSONL session persistence — append-only message log.

Adapted from claw-code session.rs: append-only JSONL, atomic writes,
session metadata, compaction support.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from koan.errors import SessionError
from koan.types import ContentBlock, Message, MessageRole, TokenUsage


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _session_id() -> str:
    return time.strftime("%Y-%m-%dT%H-%M-%S", time.localtime())


class Session:
    """Append-only JSONL session with persistence."""

    def __init__(self, session_dir: Path, session_id: str | None = None):
        self.session_id = session_id or _session_id()
        self.messages: list[Message] = []
        self._dir = session_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / f"{self.session_id}.jsonl"
        self._cumulative_tokens = 0

    @property
    def path(self) -> Path:
        return self._path

    @property
    def cumulative_tokens(self) -> int:
        return self._cumulative_tokens

    def push_user_text(self, text: str) -> None:
        msg = Message(
            role=MessageRole.USER,
            blocks=[ContentBlock(type="text", data={"text": text})],
        )
        self.messages.append(msg)
        self._persist_message(msg)

    def push_message(self, msg: Message) -> None:
        self.messages.append(msg)
        if msg.usage:
            self._cumulative_tokens += msg.usage.total
        self._persist_message(msg)

    def _persist_message(self, msg: Message) -> None:
        record = {
            "type": "message",
            "role": msg.role.value,
            "blocks": [{"type": b.type, "data": b.data} for b in msg.blocks],
            "timestamp": _iso_now(),
        }
        if msg.usage:
            record["usage"] = {
                "input_tokens": msg.usage.input_tokens,
                "output_tokens": msg.usage.output_tokens,
            }
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            raise SessionError(f"Failed to write session: {exc}") from exc

    @classmethod
    def load(cls, path: Path) -> "Session":
        """Load a session from a JSONL file."""
        session_id = path.stem
        session = cls(path.parent, session_id)
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    if record.get("type") != "message":
                        continue
                    usage = None
                    if "usage" in record:
                        u = record["usage"]
                        usage = TokenUsage(
                            input_tokens=u.get("input_tokens", 0),
                            output_tokens=u.get("output_tokens", 0),
                        )
                    msg = Message(
                        role=MessageRole(record["role"]),
                        blocks=[
                            ContentBlock(type=b["type"], data=b.get("data", {}))
                            for b in record.get("blocks", [])
                        ],
                        usage=usage,
                    )
                    session.messages.append(msg)
                    if usage:
                        session._cumulative_tokens += usage.total
        except (OSError, json.JSONDecodeError) as exc:
            raise SessionError(f"Failed to load session: {exc}") from exc
        return session
