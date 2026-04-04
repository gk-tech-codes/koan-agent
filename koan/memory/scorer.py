"""Memory scorer — ranks memories by relevance to current context.

Uses recency × relevance × importance × frequency scoring.
No embeddings — just keyword matching. Fast, local, inspectable.
"""

from __future__ import annotations

import math
import time
from typing import Any

from koan.types import Memory


def _hours_since(iso_timestamp: str) -> float:
    """Hours since an ISO timestamp."""
    if not iso_timestamp:
        return 9999.0
    try:
        # Parse ISO format: 2026-04-04T12:00:00Z
        t = time.strptime(iso_timestamp[:19], "%Y-%m-%dT%H:%M:%S")
        then = time.mktime(t)
        return max(0.0, (time.time() - then) / 3600.0)
    except Exception:
        return 9999.0


def _keyword_overlap(memory: Memory, query: str) -> float:
    """Score 0-1 based on keyword overlap between memory and query."""
    query_terms = set(query.lower().split())
    mem_terms = set((memory.content + " " + " ".join(memory.tags)).lower().split())
    if not query_terms or not mem_terms:
        return 0.0
    overlap = len(query_terms & mem_terms)
    return overlap / len(query_terms)


def recall_score(
    memory: Memory,
    query: str,
    w_recency: float = 0.2,
    w_relevance: float = 0.4,
    w_importance: float = 0.3,
    w_frequency: float = 0.1,
    decay_rate: float = 0.01,
) -> float:
    """Score a memory for recall relevance to a query."""
    recency = math.exp(-decay_rate * _hours_since(memory.updated_at))
    relevance = _keyword_overlap(memory, query)
    importance = memory.importance
    frequency = math.log(memory.recall_count + 1) / 5.0  # normalize

    return (
        w_recency * recency
        + w_relevance * relevance
        + w_importance * importance
        + w_frequency * min(frequency, 1.0)
    )


def rank_memories(
    memories: list[Memory],
    query: str,
    limit: int = 10,
    min_score: float = 0.15,
    **scoring_kwargs,
) -> list[tuple[Memory, float]]:
    """Rank memories by relevance to query. Returns (memory, score) pairs."""
    scored = []
    for m in memories:
        s = recall_score(m, query, **scoring_kwargs)
        if s >= min_score:
            scored.append((m, s))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:limit]
