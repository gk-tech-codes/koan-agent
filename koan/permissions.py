"""Permission system — mode-based tool authorization.

Adapted from claw-code permissions.rs: layered permission modes,
rule-based overrides, workspace boundary enforcement.
"""

from __future__ import annotations

import fnmatch
import os
import subprocess
from pathlib import Path
from typing import Any

from koan.types import Decision, PermissionLevel, ToolPermission

# What permission level each tool permission requires
_TOOL_LEVEL = {
    ToolPermission.READ: PermissionLevel.READ_ONLY,
    ToolPermission.WRITE: PermissionLevel.WORKSPACE_WRITE,
    ToolPermission.EXEC: PermissionLevel.FULL_ACCESS,
    ToolPermission.NET: PermissionLevel.FULL_ACCESS,
}

# Permission level ordering for comparison
_LEVEL_ORDER = {
    PermissionLevel.READ_ONLY: 0,
    PermissionLevel.WORKSPACE_WRITE: 1,
    PermissionLevel.FULL_ACCESS: 2,
}


def _detect_workspace_root() -> Path:
    """Find workspace root from git or cwd."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except Exception:
        pass
    return Path.cwd()


def _is_within_workspace(path_str: str, workspace: Path) -> bool:
    """Check if a path is inside the workspace."""
    try:
        target = Path(path_str).expanduser().resolve()
        workspace = workspace.resolve()
        return str(target).startswith(str(workspace))
    except Exception:
        return False


def _match_rule(rule: str, tool_name: str, tool_input: dict) -> bool:
    """Match a permission rule against a tool call.

    Rule formats:
      "bash"              — matches tool name
      "bash:rm *"         — matches tool name + command pattern
      "write_file:~/*"    — matches tool name + path pattern
    """
    if ":" not in rule:
        return fnmatch.fnmatch(tool_name, rule)

    rule_tool, rule_pattern = rule.split(":", 1)
    if not fnmatch.fnmatch(tool_name, rule_tool):
        return False

    # Match pattern against relevant input field
    if tool_name == "bash":
        cmd = tool_input.get("command", "")
        return fnmatch.fnmatch(cmd, rule_pattern)

    path = tool_input.get("path", "")
    return fnmatch.fnmatch(path, rule_pattern)


class Permissions:
    """Mode-based permission system with rule overrides.

    Evaluation order (same as claw-code):
      1. Deny rules — if matched, always deny
      2. Ask rules — if matched, always ask user
      3. Allow rules — if matched, always allow
      4. Mode check — compare active mode vs tool requirement
    """

    def __init__(
        self,
        mode: PermissionLevel,
        workspace_root: Path | None = None,
        rules: dict | None = None,
    ):
        self.mode = mode
        self.workspace = (workspace_root or _detect_workspace_root()).resolve()

        rules = rules or {}
        self._deny_rules: list[str] = rules.get("deny", [])
        self._ask_rules: list[str] = rules.get("ask", [])
        self._allow_rules: list[str] = rules.get("allow", [])

    def check(self, tool_name: str, tool_input: dict, tool_permission: ToolPermission | None = None) -> Decision:
        """Check if a tool call is allowed."""

        # 1. Deny rules — always deny
        for rule in self._deny_rules:
            if _match_rule(rule, tool_name, tool_input):
                return Decision.DENY

        # 2. Ask rules — always ask
        for rule in self._ask_rules:
            if _match_rule(rule, tool_name, tool_input):
                return Decision.ASK

        # 3. Allow rules — always allow
        for rule in self._allow_rules:
            if _match_rule(rule, tool_name, tool_input):
                return Decision.ALLOW

        # 4. Mode-based check
        if tool_permission is None:
            return Decision.ALLOW

        required = _TOOL_LEVEL.get(tool_permission, PermissionLevel.FULL_ACCESS)
        active = _LEVEL_ORDER[self.mode]
        needed = _LEVEL_ORDER[required]

        # Active mode meets or exceeds requirement
        if active >= needed:
            # Extra check: workspace_write mode enforces workspace boundary for writes
            if self.mode == PermissionLevel.WORKSPACE_WRITE and tool_permission == ToolPermission.WRITE:
                path = tool_input.get("path", "")
                if path and not _is_within_workspace(path, self.workspace):
                    return Decision.DENY
            return Decision.ALLOW

        # Workspace write mode + exec tool → ask
        if self.mode == PermissionLevel.WORKSPACE_WRITE and tool_permission == ToolPermission.EXEC:
            return Decision.ASK

        return Decision.DENY

    def check_with_prompt(
        self,
        tool_name: str,
        tool_input: dict,
        tool_permission: ToolPermission | None = None,
    ) -> Decision:
        """Check permission and prompt user if ASK."""
        decision = self.check(tool_name, tool_input, tool_permission)
        if decision == Decision.ASK:
            return _prompt_user(tool_name, tool_input)
        return decision


def _prompt_user(tool_name: str, tool_input: dict) -> Decision:
    """Ask the user to approve or deny a tool call."""
    preview = str(tool_input)[:120]
    print(f"\n\033[93m⚠ Permission required\033[0m")
    print(f"  Tool: \033[36m{tool_name}\033[0m")
    print(f"  Input: {preview}")

    try:
        answer = input("  Allow? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return Decision.DENY

    return Decision.ALLOW if answer in ("y", "yes") else Decision.DENY
