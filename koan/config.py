"""Configuration loader with 3-layer merge: defaults → user → project.

Mirrors the claw-code ConfigLoader pattern:
  ConfigSource::User    → ~/.koan/config.toml
  ConfigSource::Project → .koan/config.toml
  ConfigSource::Local   → CLI flags / env vars
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 12):
    import tomllib
else:
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

from koan.errors import ConfigError

from koan.log import get_logger

log = get_logger("config")

_DEFAULTS_FILE = Path(__file__).parent.parent / "config.default.toml"
_USER_DIR = Path.home() / ".koan"
_PROJECT_DIR = Path(".koan")


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. Override wins on conflicts."""
    merged = dict(base)
    for key, val in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(val, dict):
            merged[key] = _deep_merge(merged[key], val)
        else:
            merged[key] = val
    return merged


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.error("Failed to parse config %s: %s", path, exc)
        raise ConfigError(f"Failed to parse {path}: {exc}") from exc


def _apply_env(cfg: dict[str, Any]) -> dict[str, Any]:
    """Override config values from environment variables."""
    env_map = {
        "KOAN_MODE": ("agent", "mode"),
        "KOAN_PROVIDER": ("provider", "default"),
        "KOAN_PERMISSION_MODE": ("permissions", "mode"),
        "ANTHROPIC_API_KEY": ("provider", "anthropic", "api_key"),
        "OPENAI_API_KEY": ("provider", "openai", "api_key"),
        "BEDROCK_ROLE_ARN": ("provider", "bedrock", "role_arn"),
        "AWS_REGION": ("provider", "bedrock", "region"),
        "AWS_PROFILE": ("provider", "bedrock", "profile"),
    }
    for env_var, key_path in env_map.items():
        val = os.environ.get(env_var)
        if val:
            node = cfg
            for part in key_path[:-1]:
                node = node.setdefault(part, {})
            node[key_path[-1]] = val
    return cfg


class Config:
    """Immutable merged configuration."""

    def __init__(self, data: dict[str, Any], sources: list[str]):
        self._data = data
        self.sources = sources

    def get(self, *key_path: str, default: Any = None) -> Any:
        node = self._data
        for part in key_path:
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return default
        return node

    def section(self, name: str) -> dict[str, Any]:
        return dict(self._data.get(name, {}))

    @property
    def raw(self) -> dict[str, Any]:
        return dict(self._data)

    # ── Convenience accessors ────────────────────────────────────

    @property
    def mode(self) -> str:
        return self.get("agent", "mode", default="session")

    @property
    def default_provider(self) -> str:
        return self.get("provider", "default", default="ollama")

    @property
    def fallback_provider(self) -> str:
        return self.get("provider", "fallback", default="")

    @property
    def permission_mode(self) -> str:
        return self.get("permissions", "mode", default="workspace_write")

    @property
    def memory_enabled(self) -> bool:
        return self.get("memory", "enabled", default=False)

    @property
    def max_tool_iterations(self) -> int:
        return self.get("agent", "max_tool_iterations", default=25)

    @property
    def session_dir(self) -> Path:
        raw = self.get("session", "directory", default="~/.koan/sessions")
        return Path(raw).expanduser()

    @property
    def memory_dir(self) -> Path:
        raw = self.get("memory", "directory", default="~/.koan/memory")
        return Path(raw).expanduser()

    def provider_config(self, name: str) -> dict[str, Any]:
        return dict(self.get("provider", name, default={}))


def load_config(
    cli_overrides: dict[str, Any] | None = None,
    project_root: Path | None = None,
) -> Config:
    """Load config with 3-layer merge: defaults → user → project → CLI/env."""
    sources: list[str] = []

    # Layer 1: shipped defaults
    defaults = _load_toml(_DEFAULTS_FILE)
    if defaults:
        sources.append(str(_DEFAULTS_FILE))

    # Layer 2: user config
    user_path = _USER_DIR / "config.toml"
    user_cfg = _load_toml(user_path)
    if user_cfg:
        sources.append(str(user_path))

    # Layer 3: project config
    proj_dir = project_root or _PROJECT_DIR
    proj_path = proj_dir / "config.toml" if proj_dir.name != "config.toml" else proj_dir
    proj_cfg = _load_toml(proj_path)
    if proj_cfg:
        sources.append(str(proj_path))

    # Merge: defaults ← user ← project
    merged = _deep_merge(defaults, user_cfg)
    merged = _deep_merge(merged, proj_cfg)

    # Layer 4: env vars
    merged = _apply_env(merged)

    # Layer 5: CLI overrides
    if cli_overrides:
        merged = _deep_merge(merged, cli_overrides)
        sources.append("cli")

    log.debug("Config loaded from %d sources: %s", len(sources), sources)
    return Config(merged, sources)
