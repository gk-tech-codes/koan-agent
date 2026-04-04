"""Tests for the config system."""

from pathlib import Path
from koan.config import _deep_merge, _load_toml, load_config, Config


def test_deep_merge_flat():
    base = {"a": 1, "b": 2}
    override = {"b": 3, "c": 4}
    assert _deep_merge(base, override) == {"a": 1, "b": 3, "c": 4}


def test_deep_merge_nested():
    base = {"provider": {"default": "ollama", "ollama": {"model": "qwen2.5:14b"}}}
    override = {"provider": {"ollama": {"model": "llama3.1:8b"}}}
    result = _deep_merge(base, override)
    assert result["provider"]["default"] == "ollama"
    assert result["provider"]["ollama"]["model"] == "llama3.1:8b"


def test_deep_merge_empty_override():
    base = {"a": 1}
    assert _deep_merge(base, {}) == {"a": 1}


def test_load_toml_missing_file(tmp_path):
    assert _load_toml(tmp_path / "nope.toml") == {}


def test_load_toml_valid(tmp_path):
    f = tmp_path / "test.toml"
    f.write_text('[agent]\nname = "test"\n')
    result = _load_toml(f)
    assert result["agent"]["name"] == "test"


def test_load_config_defaults():
    cfg = load_config()
    assert cfg.mode in ("session", "memory")
    assert cfg.default_provider == "ollama"
    assert cfg.max_tool_iterations == 25


def test_load_config_cli_overrides():
    cfg = load_config(cli_overrides={"agent": {"mode": "memory"}, "memory": {"enabled": True}})
    assert cfg.mode == "memory"
    assert cfg.memory_enabled is True


def test_config_get_nested():
    cfg = Config({"a": {"b": {"c": 42}}}, [])
    assert cfg.get("a", "b", "c") == 42
    assert cfg.get("a", "x", default="nope") == "nope"


def test_config_provider_config():
    cfg = load_config()
    ollama = cfg.provider_config("ollama")
    assert ollama.get("type") == "openai_compat"
    assert "endpoint" in ollama


def test_config_session_dir():
    cfg = load_config()
    assert isinstance(cfg.session_dir, Path)


def test_config_memory_dir():
    cfg = load_config()
    assert isinstance(cfg.memory_dir, Path)
