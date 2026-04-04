"""Procedural memory — learned multi-step workflow playbooks.

Adapted from claw-code recovery_recipes.rs pattern: structured step sequences
with error recovery and escalation policy. Extended with learning from
session trajectories, confidence scoring, and parameterized replay.

This is the unique feature — no other CLI agent has this.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from koan.types import _iso_now


class PlaybookStep:
    """A single step in a playbook."""

    __slots__ = ("tool", "input_template", "description", "error_recovery")

    def __init__(
        self,
        tool: str,
        input_template: dict[str, Any],
        description: str = "",
        error_recovery: str = "",
    ):
        self.tool = tool
        self.input_template = input_template
        self.description = description
        self.error_recovery = error_recovery

    def to_dict(self) -> dict:
        d = {"tool": self.tool, "input": self.input_template}
        if self.description:
            d["description"] = self.description
        if self.error_recovery:
            d["error_recovery"] = self.error_recovery
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "PlaybookStep":
        return cls(
            tool=d["tool"],
            input_template=d.get("input", {}),
            description=d.get("description", ""),
            error_recovery=d.get("error_recovery", ""),
        )


class Playbook:
    """A learned multi-step workflow."""

    def __init__(self, data: dict | None = None):
        data = data or {}
        self.id: str = data.get("id", f"pb_{uuid.uuid4().hex[:8]}")
        self.name: str = data.get("name", "")
        self.triggers: list[str] = data.get("triggers", [])
        self.steps: list[PlaybookStep] = [
            PlaybookStep.from_dict(s) for s in data.get("steps", [])
        ]
        self.confidence: float = data.get("confidence", 0.5)
        self.times_used: int = data.get("times_used", 0)
        self.success_rate: float = data.get("success_rate", 1.0)
        self.learned_from: list[str] = data.get("learned_from", [])
        self.created_at: str = data.get("created_at", _iso_now())
        self.last_used: str = data.get("last_used", "")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "triggers": self.triggers,
            "steps": [s.to_dict() for s in self.steps],
            "confidence": self.confidence,
            "times_used": self.times_used,
            "success_rate": self.success_rate,
            "learned_from": self.learned_from,
            "created_at": self.created_at,
            "last_used": self.last_used,
        }

    def record_use(self, success: bool) -> None:
        """Update stats after a playbook execution."""
        self.times_used += 1
        self.last_used = _iso_now()
        # Rolling success rate
        total = self.times_used
        old_successes = self.success_rate * (total - 1)
        self.success_rate = (old_successes + (1.0 if success else 0.0)) / total
        # Confidence adjusts with use
        if success:
            self.confidence = min(1.0, self.confidence + 0.05)
        else:
            self.confidence = max(0.1, self.confidence - 0.1)

    def summary(self) -> str:
        steps_desc = " → ".join(s.tool for s in self.steps)
        return f"{self.name or self.id} ({len(self.steps)} steps: {steps_desc}) [confidence: {self.confidence:.2f}, used: {self.times_used}x]"


class PlaybookStore:
    """JSONL-backed store for learned playbooks."""

    def __init__(self, memory_dir: Path):
        self._dir = memory_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "playbooks.jsonl"
        self._playbooks: dict[str, Playbook] = {}
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
                    pb = Playbook(json.loads(line))
                    self._playbooks[pb.id] = pb
                except (json.JSONDecodeError, KeyError):
                    continue

    def _save(self):
        with open(self._path, "w", encoding="utf-8") as f:
            for pb in self._playbooks.values():
                f.write(json.dumps(pb.to_dict(), ensure_ascii=False) + "\n")

    def store(self, playbook: Playbook) -> str:
        self._playbooks[playbook.id] = playbook
        self._save()
        return playbook.id

    def get(self, playbook_id: str) -> Playbook | None:
        return self._playbooks.get(playbook_id)

    def all(self) -> list[Playbook]:
        return list(self._playbooks.values())

    def count(self) -> int:
        return len(self._playbooks)

    def delete(self, playbook_id: str) -> bool:
        if playbook_id in self._playbooks:
            del self._playbooks[playbook_id]
            self._save()
            return True
        return False

    def update(self, playbook: Playbook) -> None:
        self._playbooks[playbook.id] = playbook
        self._save()

    def find_by_trigger(self, user_input: str) -> Playbook | None:
        """Find a playbook whose trigger matches the user input."""
        input_lower = user_input.lower()
        best = None
        best_score = 0.0
        for pb in self._playbooks.values():
            for trigger in pb.triggers:
                trigger_words = set(trigger.lower().split())
                input_words = set(input_lower.split())
                if not trigger_words:
                    continue
                overlap = len(trigger_words & input_words)
                score = overlap / len(trigger_words)
                if score > best_score and score >= 0.6:
                    best = pb
                    best_score = score
        return best

    def find_similar(self, steps: list[PlaybookStep], threshold: float = 0.7) -> Playbook | None:
        """Find a playbook with a similar step sequence."""
        new_tools = [s.tool for s in steps]
        for pb in self._playbooks.values():
            existing_tools = [s.tool for s in pb.steps]
            if not new_tools or not existing_tools:
                continue
            # Compare tool sequences
            common = sum(1 for a, b in zip(new_tools, existing_tools) if a == b)
            score = common / max(len(new_tools), len(existing_tools))
            if score >= threshold:
                return pb
        return None
