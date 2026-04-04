"""Memory tools — let the LLM query and update the personal DB."""

from __future__ import annotations

from koan.tools.registry import tool

# These will be wired to the actual store at runtime via _STORE
_STORE = None


def set_memory_store(store):
    global _STORE
    _STORE = store


@tool(name="memory_recall", description="Search your personal knowledge about this user", permission="read")
def memory_recall(query: str) -> str:
    if not _STORE:
        return "(memory mode is off)"
    results = _STORE.search(query)
    if not results:
        return f"No memories found for '{query}'"
    lines = [f"Found {len(results)} memories:"]
    for m in results[:10]:
        lines.append(f"  [{m.type.value}] {m.content}")
    return "\n".join(lines)


@tool(name="memory_store", description="Save something important about this user for future sessions", permission="write")
def memory_store(content: str, type: str = "fact") -> str:
    if not _STORE:
        return "(memory mode is off)"
    from koan.types import Memory, MemoryType
    try:
        mt = MemoryType(type)
    except ValueError:
        mt = MemoryType.FACT
    from koan.memory.store import _memory_to_dict
    m = Memory(type=mt, content=content, importance=0.8, confidence=0.7)
    mid = _STORE.store(m)
    return f"Stored memory {mid}: {content}"


@tool(name="memory_forget", description="Delete a specific memory by ID", permission="write")
def memory_forget(memory_id: str) -> str:
    if not _STORE:
        return "(memory mode is off)"
    if _STORE.forget(memory_id):
        return f"Deleted memory {memory_id}"
    return f"Memory {memory_id} not found"
