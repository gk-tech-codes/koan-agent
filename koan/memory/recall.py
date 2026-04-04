"""Memory recall — query memories and format for prompt injection."""

from __future__ import annotations

from koan.memory.scorer import rank_memories
from koan.memory.store import MemoryStore
from koan.types import Memory, _iso_now


def recall(store: MemoryStore, query: str, limit: int = 10, **kwargs) -> list[Memory]:
    """Recall relevant memories for a query. Updates recall timestamps."""
    all_memories = store.all()
    if not all_memories:
        return []

    ranked = rank_memories(all_memories, query, limit=limit, **kwargs)

    # Update recall metadata
    now = _iso_now()
    for mem, score in ranked:
        store.update(mem.id, last_recalled=now, recall_count=mem.recall_count + 1)

    return [mem for mem, score in ranked]


def format_memories_for_prompt(memories: list[Memory]) -> str:
    """Format recalled memories as a context block for the system prompt."""
    if not memories:
        return ""

    lines = ["What you know about this user (from past sessions):"]
    for m in memories:
        tag_str = f" [{', '.join(m.tags)}]" if m.tags else ""
        lines.append(f"  - ({m.type.value}) {m.content}{tag_str}")

    lines.append("")
    lines.append("Use this knowledge naturally. Don't mention that you're recalling memories.")
    return "\n".join(lines)
