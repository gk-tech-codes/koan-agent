"""Tests for the permission system."""

from koan.permissions import Permissions, _match_rule, _is_within_workspace
from koan.types import Decision, PermissionLevel, ToolPermission
from pathlib import Path


def test_read_only_allows_read():
    p = Permissions(mode=PermissionLevel.READ_ONLY)
    assert p.check("read_file", {"path": "foo.py"}, ToolPermission.READ) == Decision.ALLOW


def test_read_only_denies_write():
    p = Permissions(mode=PermissionLevel.READ_ONLY)
    assert p.check("write_file", {"path": "foo.py"}, ToolPermission.WRITE) == Decision.DENY


def test_read_only_denies_exec():
    p = Permissions(mode=PermissionLevel.READ_ONLY)
    assert p.check("bash", {"command": "ls"}, ToolPermission.EXEC) == Decision.DENY


def test_workspace_write_allows_read():
    p = Permissions(mode=PermissionLevel.WORKSPACE_WRITE)
    assert p.check("read_file", {"path": "foo.py"}, ToolPermission.READ) == Decision.ALLOW


def test_workspace_write_allows_write_in_workspace():
    ws = Path.cwd()
    p = Permissions(mode=PermissionLevel.WORKSPACE_WRITE, workspace_root=ws)
    assert p.check("write_file", {"path": str(ws / "foo.py")}, ToolPermission.WRITE) == Decision.ALLOW


def test_workspace_write_denies_write_outside():
    p = Permissions(mode=PermissionLevel.WORKSPACE_WRITE, workspace_root=Path("/tmp/myproject"))
    assert p.check("write_file", {"path": "/etc/passwd"}, ToolPermission.WRITE) == Decision.DENY


def test_workspace_write_asks_for_exec():
    p = Permissions(mode=PermissionLevel.WORKSPACE_WRITE)
    assert p.check("bash", {"command": "ls"}, ToolPermission.EXEC) == Decision.ASK


def test_full_access_allows_everything():
    p = Permissions(mode=PermissionLevel.FULL_ACCESS)
    assert p.check("bash", {"command": "rm -rf /"}, ToolPermission.EXEC) == Decision.ALLOW
    assert p.check("write_file", {"path": "/etc/foo"}, ToolPermission.WRITE) == Decision.ALLOW


def test_deny_rule_overrides_mode():
    p = Permissions(
        mode=PermissionLevel.FULL_ACCESS,
        rules={"deny": ["bash:rm -rf *"]},
    )
    assert p.check("bash", {"command": "rm -rf /"}, ToolPermission.EXEC) == Decision.DENY
    assert p.check("bash", {"command": "ls"}, ToolPermission.EXEC) == Decision.ALLOW


def test_allow_rule_overrides_mode():
    p = Permissions(
        mode=PermissionLevel.READ_ONLY,
        rules={"allow": ["bash:echo *"]},
    )
    assert p.check("bash", {"command": "echo hello"}, ToolPermission.EXEC) == Decision.ALLOW
    assert p.check("bash", {"command": "ls"}, ToolPermission.EXEC) == Decision.DENY


def test_ask_rule():
    p = Permissions(
        mode=PermissionLevel.FULL_ACCESS,
        rules={"ask": ["write_file:*.config"]},
    )
    assert p.check("write_file", {"path": "app.config"}, ToolPermission.WRITE) == Decision.ASK
    assert p.check("write_file", {"path": "app.py"}, ToolPermission.WRITE) == Decision.ALLOW


def test_deny_takes_priority_over_allow():
    p = Permissions(
        mode=PermissionLevel.FULL_ACCESS,
        rules={"deny": ["bash:rm *"], "allow": ["bash:*"]},
    )
    assert p.check("bash", {"command": "rm foo"}, ToolPermission.EXEC) == Decision.DENY
    assert p.check("bash", {"command": "ls"}, ToolPermission.EXEC) == Decision.ALLOW


def test_no_permission_defaults_allow():
    p = Permissions(mode=PermissionLevel.WORKSPACE_WRITE)
    assert p.check("unknown_tool", {}, None) == Decision.ALLOW


def test_match_rule_tool_only():
    assert _match_rule("bash", "bash", {}) is True
    assert _match_rule("bash", "read_file", {}) is False


def test_match_rule_with_pattern():
    assert _match_rule("bash:rm *", "bash", {"command": "rm -rf /"}) is True
    assert _match_rule("bash:rm *", "bash", {"command": "ls"}) is False


def test_match_rule_path_pattern():
    assert _match_rule("write_file:~/*", "write_file", {"path": "~/secret"}) is True
    assert _match_rule("write_file:~/*", "write_file", {"path": "local.py"}) is False


def test_is_within_workspace():
    ws = Path("/tmp/project")
    assert _is_within_workspace("/tmp/project/src/main.py", ws) is True
    assert _is_within_workspace("/etc/passwd", ws) is False
