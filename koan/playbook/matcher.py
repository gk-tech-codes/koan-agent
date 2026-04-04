"""Playbook matcher — match user intent to learned playbooks.

When a user says something that matches a playbook trigger,
offer to run the playbook instead of starting from scratch.
"""

from __future__ import annotations

from koan.playbook.store import Playbook, PlaybookStore


def match_playbook(user_input: str, store: PlaybookStore, min_confidence: float = 0.4) -> Playbook | None:
    """Find the best matching playbook for user input."""
    match = store.find_by_trigger(user_input)
    if match and match.confidence >= min_confidence:
        return match
    return None


def format_playbook_offer(playbook: Playbook) -> str:
    """Format a playbook match as an offer to the user."""
    lines = [
        f"\033[36m◆ Learned playbook: {playbook.name or playbook.id}\033[0m",
        f"  Confidence: {playbook.confidence:.0%} | Used: {playbook.times_used}x | Success: {playbook.success_rate:.0%}",
        f"  Steps:",
    ]
    for i, step in enumerate(playbook.steps, 1):
        desc = step.description or step.tool
        lines.append(f"    {i}. {desc}")
    return "\n".join(lines)


def format_playbooks_for_prompt(playbooks: list[Playbook]) -> str:
    """Format available playbooks as context for the system prompt."""
    if not playbooks:
        return ""
    lines = ["Learned workflows available (use these when the user's request matches):"]
    for pb in playbooks:
        steps_desc = " → ".join(s.tool for s in pb.steps)
        triggers = ", ".join(f'"{t}"' for t in pb.triggers[:2])
        lines.append(f"  - {pb.name}: {steps_desc} (triggers: {triggers}, confidence: {pb.confidence:.0%})")
    return "\n".join(lines)
