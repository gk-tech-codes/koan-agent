"""Tests for the provider router."""

import asyncio
from koan.providers.router import ProviderRouter, RoutingStrategy
from koan.providers.base import BaseProvider
from koan.errors import ProviderError, MalformedToolCallError
from koan.types import Event, EventType


class MockProvider(BaseProvider):
    def __init__(self, name, events=None, error=None):
        self.name = name
        self._model = f"{name}-model"
        self._events = events or [Event(type=EventType.TEXT_DELTA, data={"text": f"from {name}"}), Event(type=EventType.MESSAGE_STOP)]
        self._error = error
        self.call_count = 0

    async def stream(self, messages, tools):
        self.call_count += 1
        if self._error:
            raise self._error
        for e in self._events:
            yield e


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


async def _collect(provider, messages=None, tools=None):
    events = []
    async for e in provider.stream(messages or [], tools or []):
        events.append(e)
    return events


def test_routes_to_primary():
    primary = MockProvider("primary")
    fallback = MockProvider("fallback")
    router = ProviderRouter(primary, fallback)

    events = _run(_collect(router))
    assert any("primary" in e.data.get("text", "") for e in events)
    assert primary.call_count == 1
    assert fallback.call_count == 0


def test_falls_back_on_provider_error():
    primary = MockProvider("primary", error=ProviderError("down"))
    fallback = MockProvider("fallback")
    router = ProviderRouter(primary, fallback, RoutingStrategy.LOCAL_FIRST)

    events = _run(_collect(router))
    assert any("fallback" in e.data.get("text", "") for e in events)
    assert primary.call_count == 1
    assert fallback.call_count == 1
    assert router._primary_failures == 1
    assert router._fallback_uses == 1


def test_falls_back_on_malformed_tool_call():
    primary = MockProvider("primary", error=MalformedToolCallError("bad json"))
    fallback = MockProvider("fallback")
    router = ProviderRouter(primary, fallback, RoutingStrategy.LOCAL_FIRST)

    events = _run(_collect(router))
    assert any("fallback" in e.data.get("text", "") for e in events)
    assert router._primary_failures == 1


def test_no_fallback_raises():
    primary = MockProvider("primary", error=ProviderError("down"))
    router = ProviderRouter(primary, fallback=None)

    try:
        _run(_collect(router))
        assert False, "should have raised"
    except ProviderError:
        pass


def test_cloud_only_no_fallback():
    primary = MockProvider("primary", error=ProviderError("down"))
    fallback = MockProvider("fallback")
    router = ProviderRouter(primary, fallback, RoutingStrategy.CLOUD_ONLY)

    try:
        _run(_collect(router))
        assert False, "should have raised"
    except ProviderError:
        pass
    assert fallback.call_count == 0


def test_fallback_only_strategy():
    primary = MockProvider("primary")
    fallback = MockProvider("fallback")
    router = ProviderRouter(primary, fallback, RoutingStrategy.FALLBACK_ONLY)

    events = _run(_collect(router))
    assert any("fallback" in e.data.get("text", "") for e in events)
    assert primary.call_count == 0
    assert fallback.call_count == 1


def test_stats():
    primary = MockProvider("ollama")
    fallback = MockProvider("bedrock")
    router = ProviderRouter(primary, fallback, RoutingStrategy.LOCAL_FIRST)

    stats = router.stats()
    assert stats["primary"] == "ollama"
    assert stats["fallback"] == "bedrock"
    assert stats["strategy"] == "local_first"


def test_is_available_primary():
    primary = MockProvider("primary")
    router = ProviderRouter(primary)
    assert router.is_available()
