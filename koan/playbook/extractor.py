"""Playbook extractor — detect tool sequences in sessions and generalize into playbooks.

Adapted from claw-code recovery_recipes.rs: structured step sequences.
Extended with generalization (parameterize specific values) and
error recovery extraction from session trajectories.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from koan.playbook.store import Playbook, PlaybookStep, PlaybookStore

from koan.log import get_logger

log = get_logger("playbook.extractor")


_MIN_CHAIN_LENGTH = 3  # minimum tool calls to form a playbook


def _extract_tool_chains(messages: list[dict]) -> list[list[dict]]:
    """Find consecutive tool-use → tool-result sequences in a session."""
    chains: list[list[dict]] = []
    current_chain: list[dict] = []

    for msg in messages:
        role = msg.get("role", "")
        blocks = msg.get("blocks", [])

        if role == "assistant":
            for b in blocks:
                if b.get("type") == "tool_use":
                    current_chain.append({
                        "tool": b["data"].get("name", ""),
                        "input": b["data"].get("input", {}),
                        "id": b["data"].get("id", ""),
                    })

        elif role == "user":
            for b in blocks:
                if b.get("type") == "tool_result":
                    data = b.get("data", {})
                    tool_id = data.get("tool_use_id", "")
                    # Attach result to matching tool call
                    for tc in current_chain:
                        if tc.get("id") == tool_id:
                            tc["output"] = data.get("output", "")
                            tc["is_error"] = data.get("is_error", False)

                elif b.get("type") == "text":
                    # User text breaks the chain — save current and start new
                    if len(current_chain) >= _MIN_CHAIN_LENGTH:
                        chains.append(current_chain)
                    current_chain = []

    # Don't forget the last chain
    if len(current_chain) >= _MIN_CHAIN_LENGTH:
        chains.append(current_chain)

    return chains


def _chain_succeeded(chain: list[dict]) -> bool:
    """Check if a tool chain completed without errors."""
    errors = sum(1 for tc in chain if tc.get("is_error", False))
    return errors == 0


def _generalize_input(tool: str, inp: dict) -> dict:
    """Replace specific values with parameterized templates."""
    generalized = {}
    for key, val in inp.items():
        if isinstance(val, str):
            # Keep the structure but note it's parameterizable
            if key == "path" and "/" in val:
                generalized[key] = val  # keep paths as-is for now
            elif key == "command":
                generalized[key] = val  # keep commands as-is
            elif key == "content" and len(val) > 100:
                generalized[key] = "$CONTENT"  # large content is parameterized
            else:
                generalized[key] = val
        else:
            generalized[key] = val
    return generalized


def _extract_description(tool: str, inp: dict) -> str:
    """Generate a human-readable description for a step."""
    if tool == "bash":
        cmd = inp.get("command", "")
        return f"Run: {cmd[:80]}"
    if tool in ("read_file", "write_file"):
        path = inp.get("path", "")
        return f"{tool}: {path}"
    if tool == "glob_search":
        return f"Find files: {inp.get('pattern', '')}"
    if tool == "grep_search":
        return f"Search for: {inp.get('pattern', '')}"
    return f"{tool}"


def _extract_error_recovery(chain: list[dict], all_messages: list[dict]) -> dict[int, str]:
    """Find error recovery patterns — when a step failed and was retried/fixed."""
    recovery = {}
    for i, tc in enumerate(chain):
        if tc.get("is_error"):
            # Look for the next successful call of the same tool
            for j in range(i + 1, len(chain)):
                if chain[j].get("tool") == tc["tool"] and not chain[j].get("is_error"):
                    recovery[i] = f"Retry with: {json.dumps(chain[j].get('input', {}))[:100]}"
                    break
    return recovery


def _extract_triggers(chain: list[dict], messages: list[dict]) -> list[str]:
    """Extract trigger phrases from user messages near the chain."""
    triggers = []
    for msg in messages:
        if msg.get("role") == "user":
            for b in msg.get("blocks", []):
                if b.get("type") == "text":
                    text = b.get("data", {}).get("text", "").strip()
                    if text and len(text) < 200:
                        triggers.append(text)
                        break  # one trigger per user message
    return triggers[:3]  # max 3 triggers


def extract_playbooks_from_session(
    session_path: Path, store: PlaybookStore
) -> list[Playbook]:
    """Extract playbooks from a completed session."""
    if not session_path.is_file():
        return []

    messages = []
    with open(session_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    chains = _extract_tool_chains(messages)
    new_playbooks = []
    log.debug("Found %d tool chains in session %s", len(chains), session_path.stem)

    for chain in chains:
        if not _chain_succeeded(chain):
            continue

        # Build steps
        steps = []
        for tc in chain:
            steps.append(PlaybookStep(
                tool=tc["tool"],
                input_template=_generalize_input(tc["tool"], tc.get("input", {})),
                description=_extract_description(tc["tool"], tc.get("input", {})),
            ))

        # Check for similar existing playbook
        similar = store.find_similar(steps)
        if similar:
            # Strengthen existing playbook
            similar.confidence = min(1.0, similar.confidence + 0.1)
            similar.learned_from.append(session_path.stem)
            store.update(similar)
            continue

        # Create new playbook
        triggers = _extract_triggers(chain, messages)
        error_recovery = _extract_error_recovery(chain, messages)

        # Apply error recovery to steps
        for idx, recovery_hint in error_recovery.items():
            if idx < len(steps):
                steps[idx].error_recovery = recovery_hint

        pb = Playbook({
            "name": _generate_name(steps),
            "triggers": triggers,
            "steps": [s.to_dict() for s in steps],
            "confidence": 0.5,
            "learned_from": [session_path.stem],
        })
        store.store(pb)
        log.info("Learned playbook '%s' (%d steps) from session %s", pb.name, len(pb.steps), session_path.stem)
        new_playbooks.append(pb)

    return new_playbooks


def _generate_name(steps: list[PlaybookStep]) -> str:
    """Generate a descriptive name from the step sequence."""
    tools = [s.tool for s in steps]
    unique = list(dict.fromkeys(tools))  # preserve order, dedupe
    return "-".join(unique[:4])
