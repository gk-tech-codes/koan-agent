"""Post-session consolidation — extract knowledge from completed sessions.

Runs after session ends in memory mode. Reviews the conversation,
extracts what's worth remembering, scores it, stores or discards.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from koan.memory.store import MemoryStore
from koan.types import Memory, MemoryType, _iso_now

from koan.log import get_logger

log = get_logger("consolidator")

# Patterns that indicate something worth remembering
_PREFERENCE_SIGNALS = [
    r"i prefer\b", r"i like\b", r"i always\b", r"i never\b",
    r"i want\b", r"don'?t use\b", r"use .+ instead",
    r"i hate\b", r"my favorite\b",
]

_FACT_SIGNALS = [
    r"i work on\b", r"my project\b", r"my team\b", r"we use\b",
    r"our stack\b", r"i'?m using\b", r"my app\b",
]

_INSTRUCTION_SIGNALS = [
    r"always\b", r"never\b", r"make sure\b", r"don'?t forget\b",
    r"remember to\b", r"from now on\b",
]

_LESSON_SIGNALS = [
    r"that fixed it", r"the issue was", r"the problem was",
    r"that worked", r"the solution", r"turns out",
]


def _detect_type(text: str) -> MemoryType | None:
    """Detect what type of memory a user statement might be."""
    lower = text.lower()
    for p in _PREFERENCE_SIGNALS:
        if re.search(p, lower):
            return MemoryType.PREFERENCE
    for p in _INSTRUCTION_SIGNALS:
        if re.search(p, lower):
            return MemoryType.INSTRUCTION
    for p in _LESSON_SIGNALS:
        if re.search(p, lower):
            return MemoryType.LESSON
    for p in _FACT_SIGNALS:
        if re.search(p, lower):
            return MemoryType.FACT
    return None


def _extract_tags(text: str) -> list[str]:
    """Extract simple tags from text."""
    # Common tech terms as tags
    tech_terms = [
        "python", "javascript", "typescript", "rust", "go", "java",
        "fastapi", "flask", "django", "react", "vue", "angular",
        "postgresql", "mysql", "mongodb", "redis", "docker", "kubernetes",
        "aws", "gcp", "azure", "git", "api", "rest", "graphql",
    ]
    lower = text.lower()
    return [t for t in tech_terms if t in lower]


def _score_candidate(content: str, mem_type: MemoryType, store: MemoryStore) -> float:
    """Score a candidate memory for storage worthiness."""
    # Novelty: is this new?
    similar = store.find_similar(content, threshold=0.6)
    novelty = 0.2 if similar else 1.0

    # Specificity: personal vs generic
    personal_words = {"i", "my", "we", "our", "prefer", "always", "never"}
    words = set(content.lower().split())
    specificity = min(1.0, len(words & personal_words) / 2.0)

    # Type bonus: instructions and lessons are more valuable
    type_bonus = {
        MemoryType.INSTRUCTION: 0.3,
        MemoryType.LESSON: 0.25,
        MemoryType.PREFERENCE: 0.2,
        MemoryType.FACT: 0.1,
        MemoryType.PATTERN: 0.15,
        MemoryType.REFERENCE: 0.1,
    }.get(mem_type, 0.0)

    return 0.3 * novelty + 0.3 * specificity + 0.2 * type_bonus + 0.2 * 0.5


def extract_candidates_from_session(session_path: Path) -> list[dict]:
    """Extract memory candidates from a session JSONL file."""
    candidates = []

    if not session_path.is_file():
        return candidates

    with open(session_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Only look at user messages
            if record.get("role") != "user":
                continue

            for block in record.get("blocks", []):
                if block.get("type") != "text":
                    continue
                text = block.get("data", {}).get("text", "").strip()
                if len(text) < 10:
                    continue

                mem_type = _detect_type(text)
                if mem_type:
                    candidates.append({
                        "content": text,
                        "type": mem_type,
                        "tags": _extract_tags(text),
                    })

    return candidates


def consolidate_session(session_path: Path, store: MemoryStore, threshold: float = 0.4) -> dict:
    """Run post-session consolidation. Returns stats."""
    candidates = extract_candidates_from_session(session_path)
    session_id = session_path.stem
    log.info("Consolidating session %s: %d candidates found", session_id, len(candidates))
    now = _iso_now()

    stored = 0
    updated = 0
    discarded = 0

    for c in candidates:
        score = _score_candidate(c["content"], c["type"], store)

        if score < threshold:
            discarded += 1
            continue

        # Check if similar memory exists
        similar = store.find_similar(c["content"], threshold=0.6)
        if similar:
            # Update existing — boost confidence
            new_conf = min(1.0, similar.confidence + 0.1)
            store.update(
                similar.id,
                confidence=new_conf,
                updated_at=now,
                source_sessions=similar.source_sessions + [session_id],
            )
            updated += 1
        else:
            # Store new memory
            store.store(Memory(
                type=c["type"],
                content=c["content"],
                tags=c["tags"],
                confidence=0.5 + score * 0.3,
                importance=score,
                source_sessions=[session_id],
            ))
            stored += 1

    # Decay old memories
    decayed = 0
    deleted = 0
    for m in store.all():
        hours = _hours_since_update(m)
        if hours > 24 and m.recall_count == 0:
            new_conf = m.confidence * 0.95
            if new_conf < 0.1:
                store.forget(m.id)
                deleted += 1
            else:
                store.update(m.id, confidence=new_conf)
                decayed += 1

    # Deduplicate — merge similar memories
    deduped = store.deduplicate(threshold=0.6)

    log.info("Consolidation complete: %d stored, %d updated, %d discarded, %d decayed, %d deleted, %d deduped",
             stored, updated, discarded, decayed, deleted, deduped)

    return {
        "candidates": len(candidates),
        "stored": stored,
        "updated": updated,
        "discarded": discarded,
        "decayed": decayed,
        "deleted": deleted,
        "deduped": deduped,
    }


def consolidate_session_with_episodes(
    session_path: Path, store: MemoryStore, episodic_store=None, playbook_store=None, threshold: float = 0.4
) -> dict:
    """Run full consolidation: semantic + episodic + procedural."""
    stats = consolidate_session(session_path, store, threshold)

    # Episodic: compress session into an episode
    if episodic_store is not None:
        from koan.memory.episodic import extract_episode
        episode = extract_episode(session_path)
        if episode:
            episodic_store.store(episode)
            stats["episode"] = True
        else:
            stats["episode"] = False

    # Procedural: extract playbooks from tool sequences
    if playbook_store is not None:
        from koan.playbook.extractor import extract_playbooks_from_session
        new_playbooks = extract_playbooks_from_session(session_path, playbook_store)
        stats["playbooks_learned"] = len(new_playbooks)
    else:
        stats["playbooks_learned"] = 0

    return stats
    from koan.memory.scorer import _hours_since
    return _hours_since(m.updated_at)


def _hours_since_update(m: Memory) -> float:
    from koan.memory.scorer import _hours_since
    return _hours_since(m.updated_at)
