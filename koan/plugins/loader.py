"""Plugin loader — auto-discover plugins from directories.

Scans plugin directories for .py files, imports them to trigger
@hook decorator registration. Simple drop-in model.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def discover_plugins(directories: list[str]) -> list[str]:
    """Import all .py files from plugin directories. Returns loaded plugin names."""
    loaded = []

    for dir_str in directories:
        plugin_dir = Path(dir_str).expanduser()
        if not plugin_dir.is_dir():
            continue

        for py_file in sorted(plugin_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue

            module_name = f"koan_plugin_{py_file.stem}"
            try:
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                    loaded.append(py_file.stem)
            except Exception as exc:
                print(f"\033[33m⚠ Plugin {py_file.name} failed to load: {exc}\033[0m")

    return loaded
