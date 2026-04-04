"""Tests for the memory store."""

import tempfile
from pathlib import Path

from koan.memory.store import MemoryStore
from koan.types import Memory, MemoryType


def _tmp_store():
    d = tempfile.mkdtemp()
    return MemoryStore(Path(d))


def test_store_and_get():
    s = _tmp_store()
    m = Memory(type=MemoryType.FACT, content="User likes Python")
    mid = s.store(m)
    assert s.get(mid) is not None
    assert s.get(mid).content == "User likes Python"


def test_count():
    s = _tmp_store()
    assert s.count() == 0
    s.store(Memory(content="one"))
    s.store(Memory(content="two"))
    assert s.count() == 2


def test_forget():
    s = _tmp_store()
    m = Memory(content="forget me")
    mid = s.store(m)
    assert s.count() == 1
    assert s.forget(mid) is True
    assert s.count() == 0
    assert s.get(mid) is None


def test_forget_nonexistent():
    s = _tmp_store()
    assert s.forget("nope") is False


def test_update():
    s = _tmp_store()
    m = Memory(content="old", confidence=0.5)
    mid = s.store(m)
    s.update(mid, confidence=0.9, content="new")
    updated = s.get(mid)
    assert updated.confidence == 0.9
    assert updated.content == "new"


def test_update_nonexistent():
    s = _tmp_store()
    assert s.update("nope", content="x") is False


def test_search():
    s = _tmp_store()
    s.store(Memory(content="User prefers FastAPI for web", tags=["python", "web"]))
    s.store(Memory(content="User uses PostgreSQL", tags=["database"]))
    s.store(Memory(content="User likes dark mode", tags=["ui"]))

    results = s.search("FastAPI")
    assert len(results) == 1
    assert "FastAPI" in results[0].content

    results = s.search("python")
    assert len(results) == 1

    results = s.search("user")
    assert len(results) == 3


def test_search_multi_term():
    s = _tmp_store()
    s.store(Memory(content="User prefers FastAPI for Python web apps"))
    s.store(Memory(content="User likes Flask"))

    results = s.search("FastAPI Python")
    assert len(results) == 1


def test_find_similar():
    s = _tmp_store()
    s.store(Memory(content="User prefers FastAPI over Flask"))
    s.store(Memory(content="User uses PostgreSQL database"))

    match = s.find_similar("User prefers FastAPI for APIs")
    assert match is not None
    assert "FastAPI" in match.content

    no_match = s.find_similar("completely unrelated topic xyz")
    assert no_match is None


def test_by_type():
    s = _tmp_store()
    s.store(Memory(type=MemoryType.PREFERENCE, content="likes tabs"))
    s.store(Memory(type=MemoryType.FACT, content="uses Mac"))
    s.store(Memory(type=MemoryType.PREFERENCE, content="likes dark mode"))

    prefs = s.by_type(MemoryType.PREFERENCE)
    assert len(prefs) == 2
    facts = s.by_type(MemoryType.FACT)
    assert len(facts) == 1


def test_persistence():
    d = tempfile.mkdtemp()
    path = Path(d)

    s1 = MemoryStore(path)
    s1.store(Memory(id="mem_persist", content="remember me"))

    s2 = MemoryStore(path)
    assert s2.count() == 1
    assert s2.get("mem_persist").content == "remember me"


def test_all():
    s = _tmp_store()
    s.store(Memory(content="one"))
    s.store(Memory(content="two"))
    assert len(s.all()) == 2
