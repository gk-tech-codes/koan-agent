"""Kōan UI components — branded visuals for the CLI.

Banner, status bar, memory recall display, review display.
"""

from __future__ import annotations

import time
from pathlib import Path


# Colors
B = "\033[1m"       # bold
D = "\033[90m"      # dim
R = "\033[0m"       # reset
BLUE = "\033[34m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
WHITE = "\033[97m"


def _pad(text: str, width: int) -> str:
    """Pad text to width, accounting for ANSI escape codes."""
    import re
    visible = re.sub(r'\033\[[0-9;]*m', '', text)
    padding = max(0, width - len(visible))
    return text + " " * padding


def banner(mode: str, provider: str, memory_count: int = 0, playbook_count: int = 0,
           episode_count: int = 0, review: bool = False) -> str:
    """Render the startup banner."""
    W = 51  # inner width

    flags = []
    if mode == "memory":
        flags.append(GREEN + "memory" + R)
    if review:
        flags.append(YELLOW + "review" + R)
    flag_str = " │ ".join(flags) if flags else D + "session" + R

    mem_str = CYAN + str(memory_count) + R + " memories" if memory_count else D + "0 memories" + R
    parts = [mem_str]
    if playbook_count:
        parts.append(CYAN + str(playbook_count) + R + " playbooks")
    if episode_count:
        parts.append(CYAN + str(episode_count) + R + " episodes")
    stats_line = " │ ".join(parts)

    provider_line = "Provider: " + WHITE + provider + R + " │ Mode: " + flag_str

    hour = time.localtime().tm_hour
    greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"

    top = D + "╔" + "═" * W + "╗" + R
    bot = D + "╚" + "═" * W + "╝" + R
    emp = D + "║" + R + " " * W + D + "║" + R

    def row(content):
        return D + "║" + R + "   " + _pad(content, W - 4) + " " + D + "║" + R

    return "\n".join([
        top,
        emp,
        row(B + BLUE + "◜ K Ō A N" + R),
        row(D + "The AI agent that learns your workflows" + R),
        emp,
        row(stats_line),
        row(provider_line),
        emp,
        bot,
        "  " + D + greeting + ". Type /help for commands." + R,
        "",
    ])


def status_bar(tokens: int = 0, context_pct: int = 0, tools_used: int = 0,
               memory_on: bool = False, cost: float = 0.0) -> str:
    """Render the bottom status bar."""
    ctx_color = GREEN if context_pct < 60 else YELLOW if context_pct < 80 else RED
    mem_icon = f"{GREEN}●{R}" if memory_on else f"{D}○{R}"

    parts = [
        f"◈ {ctx_color}{context_pct}%{R}",
        f"{tokens:,} tok",
        f"${cost:.2f}",
        f"{tools_used} tools",
        f"mem {mem_icon}",
    ]
    bar = " │ ".join(parts)
    return f"{D}{'─' * 53}{R}\n {bar}\n{D}{'─' * 53}{R}"


def memory_recall_box(memories: list, episodes: list = None, playbooks: list = None) -> str:
    """Show what memories were recalled for this turn."""
    if not memories and not episodes and not playbooks:
        return ""

    lines = [f"  {D}┌─ RECALLED ────────────────────────────────────┐{R}"]

    for m in memories[:5]:
        type_color = GREEN if m.get("type") == "preference" else CYAN if m.get("type") == "fact" else YELLOW
        content = m.get("content", "")[:50]
        lines.append(f"  {D}│{R} {D}←{R} {type_color}[{m.get('type', '?')}]{R} {content}")

    if episodes:
        for e in episodes[:2]:
            lines.append(f"  {D}│{R} {D}←{R} {MAGENTA}[episode]{R} {e[:50]}")

    if playbooks:
        for p in playbooks[:2]:
            lines.append(f"  {D}│{R} {D}←{R} {YELLOW}[playbook]{R} {p[:50]}")

    lines.append(f"  {D}└───────────────────────────────────────────────┘{R}")
    return "\n".join(lines)


def review_box(review_log: list, approved: bool, rounds: int) -> str:
    """Show the review process summary."""
    status = f"{GREEN}✓ APPROVED{R}" if approved else f"{YELLOW}⚠ MAX ROUNDS{R}"

    lines = [f"  {D}┌─ REVIEW ──────────────────────────────────────┐{R}"]

    for entry in review_log:
        r = entry.get("round", 0)
        verdict = entry.get("verdict", "?")
        feedback = entry.get("feedback", "")

        if verdict == "REVISE":
            # Extract issues from feedback
            issues = [l.strip() for l in feedback.split("\n") if l.strip().startswith("-") or l.strip().startswith("•")][:3]
            lines.append(f"  {D}│{R} Round {r}: {YELLOW}Critic found issues{R}")
            for issue in issues:
                lines.append(f"  {D}│{R}   {YELLOW}⚠{R} {issue[:50]}")
        else:
            lines.append(f"  {D}│{R} Round {r}: {GREEN}All issues fixed → ✓ APPROVED{R}")

    lines.append(f"  {D}│{R}")
    lines.append(f"  {D}│{R} Result: {status} after {rounds} round(s)")
    lines.append(f"  {D}└───────────────────────────────────────────────┘{R}")
    return "\n".join(lines)


def tip() -> str:
    """Random startup tip."""
    import random
    tips = [
        "Use --review for peer-reviewed code generation",
        "Use --memory to build compounding knowledge",
        "Use /context to check context window usage",
        "Use /undo to revert file changes (with --undo flag)",
        "Use /why to see reasoning (with --explain flag)",
        "Playbooks are learned automatically from multi-step tasks",
        "Memory consolidation runs after each session ends",
    ]
    return f"  {D}💡 {random.choice(tips)}{R}"
