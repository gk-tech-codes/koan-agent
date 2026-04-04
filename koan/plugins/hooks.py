"""Plugin hook system — decorator-based extensibility.

Adapted from claw-code plugins/hooks.rs: pre/post tool hooks with
allow/deny/modify semantics. Simplified to Python decorators instead
of shell scripts.

Hook points:
  on_session_start  — session begins
  on_session_end    — session ends (before consolidation)
  on_turn_start     — user message received
  on_turn_end       — assistant finished responding
  before_tool       — tool about to execute (can deny/modify)
  after_tool        — tool finished (can modify output)
  on_tool_error     — tool failed
  on_memory_store   — new memory being stored
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

from koan.types import HookResult

# Valid hook event names
HOOK_EVENTS = frozenset({
    "on_session_start",
    "on_session_end",
    "on_turn_start",
    "on_turn_end",
    "before_tool",
    "after_tool",
    "on_tool_error",
    "on_memory_store",
})

# Global hook registry
_HOOKS: dict[str, list[Callable]] = defaultdict(list)


def hook(event: str):
    """Decorator to register a function as a plugin hook."""
    if event not in HOOK_EVENTS:
        raise ValueError(f"Unknown hook event: {event}. Valid: {sorted(HOOK_EVENTS)}")

    def decorator(fn: Callable) -> Callable:
        _HOOKS[event].append(fn)
        return fn

    return decorator


def get_hooks() -> dict[str, list[Callable]]:
    return dict(_HOOKS)


def clear_hooks():
    _HOOKS.clear()


async def dispatch(event: str, **kwargs) -> HookResult:
    """Run all hooks for an event. Returns combined result.

    For before_tool: if any hook denies, the tool is blocked.
    For other events: hooks run for side effects, results merged.
    """
    result = HookResult.allow()

    for handler in _HOOKS.get(event, []):
        try:
            r = handler(**kwargs)
            # Support async hooks
            import inspect
            if inspect.isawaitable(r):
                r = await r

            if r is None:
                continue

            if isinstance(r, HookResult):
                if r.denied:
                    return r  # short-circuit on deny
                result.messages.extend(r.messages)
                if r.updated_input is not None:
                    result.updated_input = r.updated_input

        except Exception as exc:
            result.messages.append(f"Hook error ({handler.__name__}): {exc}")

    return result
