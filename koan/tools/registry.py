"""Tool registry — @tool decorator with auto-schema generation.

Adapted from claw-code tools/lib.rs: ToolSpec + GlobalToolRegistry.
Tools are decorated functions. Schemas auto-generated from type hints.
"""

from __future__ import annotations

import inspect
import importlib
import pkgutil
from pathlib import Path
from typing import Any, Callable, get_type_hints

from koan.types import ToolPermission, ToolResult, ToolSchema


# Python type → JSON schema type
_TYPE_MAP = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def _schema_from_hints(fn: Callable) -> dict[str, Any]:
    """Generate JSON schema from function type hints."""
    hints = get_type_hints(fn)
    sig = inspect.signature(fn)
    properties = {}
    required = []

    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue
        hint = hints.get(name, str)
        json_type = _TYPE_MAP.get(hint, "string")
        properties[name] = {"type": json_type}
        if param.default is inspect.Parameter.empty:
            required.append(name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


class ToolDef:
    """A registered tool definition."""

    __slots__ = ("name", "description", "permission", "schema", "fn")

    def __init__(
        self,
        name: str,
        description: str,
        permission: ToolPermission,
        schema: dict[str, Any],
        fn: Callable,
    ):
        self.name = name
        self.description = description
        self.permission = permission
        self.schema = schema
        self.fn = fn

    def to_tool_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            permission=self.permission,
            input_schema=self.schema,
        )


class ToolRegistry:
    """Global tool registry — discovers and executes tools."""

    def __init__(self):
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool_def: ToolDef) -> None:
        self._tools[tool_def.name] = tool_def

    def get(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    def schemas(self) -> list[ToolSchema]:
        return [t.to_tool_schema() for t in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools.keys())

    async def execute(self, name: str, tool_input: dict[str, Any]) -> ToolResult:
        tool_def = self._tools.get(name)
        if not tool_def:
            return ToolResult(
                tool_use_id="",
                output=f"Unknown tool: {name}",
                is_error=True,
            )
        try:
            result = tool_def.fn(**tool_input)
            # Support both sync and async tools
            if inspect.isawaitable(result):
                result = await result
            return ToolResult(tool_use_id="", output=str(result))
        except Exception as exc:
            return ToolResult(tool_use_id="", output=str(exc), is_error=True)


# ── Global registry singleton ────────────────────────────────────────

_REGISTRY = ToolRegistry()


def tool(name: str, description: str, permission: str = "read"):
    """Decorator to register a function as a tool."""
    perm = ToolPermission(permission)

    def decorator(fn: Callable) -> Callable:
        schema = _schema_from_hints(fn)
        _REGISTRY.register(ToolDef(name, description, perm, schema, fn))
        return fn

    return decorator


def get_registry() -> ToolRegistry:
    return _REGISTRY


def discover_tools(package_path: str = "koan.tools") -> None:
    """Import all modules in the tools package to trigger @tool registration."""
    try:
        pkg = importlib.import_module(package_path)
        if hasattr(pkg, "__path__"):
            for _, mod_name, _ in pkgutil.iter_modules(pkg.__path__):
                importlib.import_module(f"{package_path}.{mod_name}")
    except ImportError:
        pass
