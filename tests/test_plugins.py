"""Tests for the plugin hook system."""

import asyncio
from koan.plugins.hooks import hook, dispatch, clear_hooks, get_hooks, HOOK_EVENTS
from koan.types import HookResult


def setup():
    clear_hooks()


def test_hook_registration():
    setup()

    @hook("before_tool")
    def my_hook(**kwargs):
        pass

    hooks = get_hooks()
    assert "before_tool" in hooks
    assert len(hooks["before_tool"]) == 1


def test_hook_dispatch_allow():
    setup()

    @hook("before_tool")
    def allow_all(**kwargs):
        return HookResult.allow(["ok"])

    result = asyncio.get_event_loop().run_until_complete(
        dispatch("before_tool", tool_name="bash", tool_input={})
    )
    assert not result.denied
    assert "ok" in result.messages


def test_hook_dispatch_deny():
    setup()

    @hook("before_tool")
    def block_rm(**kwargs):
        if "rm" in kwargs.get("tool_input", {}).get("command", ""):
            return HookResult.deny("blocked rm")
        return None

    result = asyncio.get_event_loop().run_until_complete(
        dispatch("before_tool", tool_name="bash", tool_input={"command": "rm -rf /"})
    )
    assert result.denied
    assert "blocked rm" in result.messages


def test_hook_dispatch_no_hooks():
    setup()
    result = asyncio.get_event_loop().run_until_complete(
        dispatch("before_tool", tool_name="bash", tool_input={})
    )
    assert not result.denied


def test_hook_dispatch_multiple():
    setup()

    @hook("after_tool")
    def hook1(**kwargs):
        return HookResult.allow(["from hook1"])

    @hook("after_tool")
    def hook2(**kwargs):
        return HookResult.allow(["from hook2"])

    result = asyncio.get_event_loop().run_until_complete(
        dispatch("after_tool", tool_name="bash", output="done")
    )
    assert "from hook1" in result.messages
    assert "from hook2" in result.messages


def test_hook_deny_short_circuits():
    setup()
    called = []

    @hook("before_tool")
    def deny_first(**kwargs):
        called.append("first")
        return HookResult.deny("nope")

    @hook("before_tool")
    def second(**kwargs):
        called.append("second")
        return None

    result = asyncio.get_event_loop().run_until_complete(
        dispatch("before_tool", tool_name="bash", tool_input={})
    )
    assert result.denied
    assert called == ["first"]  # second never ran


def test_hook_error_handled():
    setup()

    @hook("after_tool")
    def bad_hook(**kwargs):
        raise ValueError("oops")

    result = asyncio.get_event_loop().run_until_complete(
        dispatch("after_tool", tool_name="bash", output="done")
    )
    assert not result.denied
    assert any("oops" in m for m in result.messages)


def test_all_events_valid():
    assert "before_tool" in HOOK_EVENTS
    assert "after_tool" in HOOK_EVENTS
    assert "on_session_start" in HOOK_EVENTS
    assert "on_turn_end" in HOOK_EVENTS
    assert len(HOOK_EVENTS) == 8
