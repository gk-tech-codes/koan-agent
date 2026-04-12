"""Memory store — JSONL-based personal knowledge database.

Read, write, search, delete memories. All stored as simple JSONL files.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from koan.types import Memory, MemoryType

from koan.log import get_logger

log = get_logger("memory.store")


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
        """Store a new memory. Deduplicates against existing content."""
        # Check for duplicate or near-duplicate content
        existing = self.find_similar(memory.content, threshold=0.8)
        if existing:
            # Strengthen existing instead of creating duplicate
            from koan.types import _iso_now
            new_conf = min(1.0, existing.confidence + 0.1)
            self.update(existing.id, confidence=new_conf, updated_at=_iso_now())
            log.debug("Deduplicated — strengthened existing %s instead of storing new", existing.id)
            return existing.id

        self._memories[memory.id] = memory
        self._save()
        log.debug("Stored [%s] %s: %s", memory.type.value, memory.id, memory.content[:60])
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
            content = self._memories[memory_id].content[:60]
            del self._memories[memory_id]
            self._save()
            log.info("Deleted memory %s: %s", memory_id, content)
            return True
        log.warning("Forget failed — memory %s not found", memory_id)
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

    def deduplicate(self, threshold: float = 0.6) -> int:
        """Merge duplicate memories. Keeps highest-confidence version, boosts it.
        Returns number of duplicates removed."""
        ids = list(self._memories.keys())
        to_remove = set()
        merged = 0

        for i, id_a in enumerate(ids):
            if id_a in to_remove:
                continue
            mem_a = self._memories[id_a]
            words_a = set(mem_a.content.lower().split())

            for id_b in ids[i + 1:]:
                if id_b in to_remove:
                    continue
                mem_b = self._memories[id_b]
                words_b = set(mem_b.content.lower().split())

                if not words_a or not words_b:
                    continue
                overlap = len(words_a & words_b) / min(len(words_a), len(words_b))

                if overlap >= threshold:
                    # Keep the one with higher confidence, boost it
                    if mem_a.confidence >= mem_b.confidence:
                        mem_a.confidence = min(1.0, mem_a.confidence + 0.1)
                        mem_a.recall_count += mem_b.recall_count
                        to_remove.add(id_b)
                    else:
                        mem_b.confidence = min(1.0, mem_b.confidence + 0.1)
                        mem_b.recall_count += mem_a.recall_count
                        to_remove.add(id_a)
                        break  # id_a is removed, stop comparing it
                    merged += 1

        for rid in to_remove:
            del self._memories[rid]

        if merged > 0:
            self._save()
            log.info("Deduplicated: merged %d memories, %d remaining", merged, len(self._memories))

        return merged
