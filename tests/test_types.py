"""Tests for core types."""

from koan.types import (
    Decision,
    Event,
    EventType,
    HookResult,
    Memory,
    MemoryType,
    Message,
    MessageRole,
    Mode,
    PermissionLevel,
    ToolPermission,
    ToolResult,
    ToolSchema,
    ToolUse,
    TokenUsage,
)


def test_mode_values():
    assert Mode.SESSION.value == "session"
    assert Mode.MEMORY.value == "memory"


def test_permission_level_values():
    assert PermissionLevel.READ_ONLY.value == "read_only"
    assert PermissionLevel.WORKSPACE_WRITE.value == "workspace_write"
    assert PermissionLevel.FULL_ACCESS.value == "full_access"


def test_tool_permission_values():
    assert ToolPermission.READ.value == "read"
    assert ToolPermission.EXEC.value == "exec"


def test_event_creation():
    e = Event(type=EventType.TEXT_DELTA, data={"text": "hello"})
    assert e.type == EventType.TEXT_DELTA
    assert e.data["text"] == "hello"


def test_tool_use():
    t = ToolUse(id="t1", name="bash", input={"command": "ls"})
    assert t.name == "bash"


def test_tool_result():
    r = ToolResult(tool_use_id="t1", output="file.txt")
    assert not r.is_error


def test_tool_result_error():
    r = ToolResult(tool_use_id="t1", output="fail", is_error=True)
    assert r.is_error


def test_message():
    m = Message(role=MessageRole.USER)
    assert m.role == MessageRole.USER
    assert m.blocks == []
    assert m.usage is None


def test_token_usage_total():
    u = TokenUsage(input_tokens=100, output_tokens=50)
    assert u.total == 150


def test_tool_schema():
    s = ToolSchema(
        name="bash",
        description="Run a command",
        permission=ToolPermission.EXEC,
        input_schema={"type": "object", "properties": {"command": {"type": "string"}}},
    )
    assert s.name == "bash"
    assert s.permission == ToolPermission.EXEC


def test_memory_auto_id():
    m = Memory(type=MemoryType.PREFERENCE, content="likes tabs")
    assert m.id.startswith("mem_")
    assert len(m.id) == 12
    assert m.created_at != ""
    assert m.updated_at != ""


def test_memory_explicit_id():
    m = Memory(id="mem_custom", content="test")
    assert m.id == "mem_custom"


def test_hook_result_allow():
    r = HookResult.allow(["info"])
    assert not r.denied
    assert r.messages == ["info"]


def test_hook_result_deny():
    r = HookResult.deny("not allowed")
    assert r.denied
    assert "not allowed" in r.messages


def test_decision_enum():
    assert Decision.ALLOW.value == "allow"
    assert Decision.DENY.value == "deny"
    assert Decision.ASK.value == "ask"
