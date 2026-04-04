"""Memory store — JSONL-based personal knowledge database.

Read, write, search, delete memories. All stored as simple JSONL files.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from koan.types import Memory, MemoryType


def _memory_to_dict(m: Memory) -> dict:
    return {
        "id": m.id,
        "type": m.type.value,
        "content": m.content,
        "tags": m.tags,
        "confidence": m.confidence,
        "importance": m.importance,
        "created_at": m.created_at,
        "updated_at": m.updated_at,
        "last_recalled": m.last_recalled,
        "recall_count": m.recall_count,
        "source_sessions": m.source_sessions,
    }


def _dict_to_memory(d: dict) -> Memory:
    return Memory(
        id=d["id"],
        type=MemoryType(d.get("type", "fact")),
        content=d.get("content", ""),
        tags=d.get("tags", []),
        confidence=d.get("confidence", 0.5),
        importance=d.get("importance", 0.5),
        created_at=d.get("created_at", ""),
        updated_at=d.get("updated_at", ""),
        last_recalled=d.get("last_recalled", ""),
        recall_count=d.get("recall_count", 0),
        source_sessions=d.get("source_sessions", []),
    )


class MemoryStore:
    """JSONL-backed personal knowledge store."""

    def __init__(self, memory_dir: Path):
        self._dir = memory_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "store.jsonl"
        self._memories: dict[str, Memory] = {}
        self._load()

    def _load(self):
        """Load all memories from JSONL file."""
        if not self._path.is_file():
            return
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    m = _dict_to_memory(d)
                    self._memories[m.id] = m
                except (json.JSONDecodeError, KeyError):
                    continue

    def _save(self):
        """Rewrite the full JSONL file."""
        with open(self._path, "w", encoding="utf-8") as f:
            for m in self._memories.values():
                f.write(json.dumps(_memory_to_dict(m), ensure_ascii=False) + "\n")

    def store(self, memory: Memory) -> str:
        """Store a new memory. Returns the memory ID."""
        self._memories[memory.id] = memory
        self._save()
        return memory.id

    def get(self, memory_id: str) -> Memory | None:
        return self._memories.get(memory_id)

    def update(self, memory_id: str, **kwargs) -> bool:
        """Update fields on an existing memory."""
        m = self._memories.get(memory_id)
        if not m:
            return False
        for key, val in kwargs.items():
            if hasattr(m, key):
                setattr(m, key, val)
        from koan.types import _iso_now
        m.updated_at = _iso_now()
        self._save()
        return True

    def forget(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        if memory_id in self._memories:
            del self._memories[memory_id]
            self._save()
            return True
        return False

    def all(self) -> list[Memory]:
        return list(self._memories.values())

    def count(self) -> int:
        return len(self._memories)

    def search(self, query: str) -> list[Memory]:
        """Simple keyword search across content and tags."""
        query_lower = query.lower()
        terms = query_lower.split()
        results = []
        for m in self._memories.values():
            text = (m.content + " " + " ".join(m.tags)).lower()
            if all(t in text for t in terms):
                results.append(m)
        return results

    def find_similar(self, content: str, threshold: float = 0.5) -> Memory | None:
        """Find a memory with similar content (simple word overlap)."""
        content_words = set(content.lower().split())
        best = None
        best_score = 0.0
        for m in self._memories.values():
            mem_words = set(m.content.lower().split())
            if not content_words or not mem_words:
                continue
            overlap = len(content_words & mem_words)
            score = overlap / max(len(content_words), len(mem_words))
            if score > best_score and score >= threshold:
                best = m
                best_score = score
        return best

    def by_type(self, memory_type: MemoryType) -> list[Memory]:
        return [m for m in self._memories.values() if m.type == memory_type]
