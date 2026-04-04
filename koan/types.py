"""Core types, protocols, and enums for the entire system.

Every component implements a Protocol defined here.
This file has ZERO dependencies on other koan modules.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Protocol, runtime_checkable


# ── Enums ────────────────────────────────────────────────────────────

class Mode(Enum):
    SESSION = "session"
    MEMORY = "memory"


class PermissionLevel(Enum):
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    FULL_ACCESS = "full_access"


class ToolPermission(Enum):
    READ = "read"
    WRITE = "write"
    EXEC = "exec"
    NET = "net"


class Decision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class EventType(Enum):
    TEXT_DELTA = "text_delta"
    TOOL_USE = "tool_use"
    USAGE = "usage"
    MESSAGE_STOP = "message_stop"


class MessageRole(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class MemoryType(Enum):
    PREFERENCE = "preference"
    FACT = "fact"
    PATTERN = "pattern"
    LESSON = "lesson"
    REFERENCE = "reference"
    INSTRUCTION = "instruction"


# ── Data classes ─────────────────────────────────────────────────────

@dataclass
class Event:
    type: EventType
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolUse:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class ToolResult:
    tool_use_id: str
    output: str
    is_error: bool = False


@dataclass
class ContentBlock:
    """A single block in a message — text or tool use or tool result."""
    type: str  # "text", "tool_use", "tool_result"
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    role: MessageRole
    blocks: list[ContentBlock] = field(default_factory=list)
    usage: TokenUsage | None = None


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class ToolSchema:
    name: str
    description: str
    permission: ToolPermission
    input_schema: dict[str, Any]


@dataclass
class Memory:
    id: str = ""
    type: MemoryType = MemoryType.FACT
    content: str = ""
    tags: list[str] = field(default_factory=list)
    confidence: float = 0.5
    importance: float = 0.5
    created_at: str = ""
    updated_at: str = ""
    last_recalled: str = ""
    recall_count: int = 0
    source_sessions: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.id:
            self.id = f"mem_{uuid.uuid4().hex[:8]}"
        now = _iso_now()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now


@dataclass
class HookResult:
    denied: bool = False
    messages: list[str] = field(default_factory=list)
    updated_input: dict[str, Any] | None = None

    @classmethod
    def allow(cls, messages: list[str] | None = None) -> HookResult:
        return cls(messages=messages or [])

    @classmethod
    def deny(cls, reason: str) -> HookResult:
        return cls(denied=True, messages=[reason])


# ── Protocols (interfaces) ───────────────────────────────────────────

@runtime_checkable
class Provider(Protocol):
    name: str

    async def stream(
        self, messages: list[Message], tools: list[ToolSchema]
    ) -> AsyncIterator[Event]: ...

    def supports_tool_use(self) -> bool: ...

    def is_available(self) -> bool: ...


@runtime_checkable
class ToolExecutor(Protocol):
    async def execute(self, name: str, input: dict[str, Any]) -> ToolResult: ...


@runtime_checkable
class MemoryStore(Protocol):
    async def recall(self, query: str, limit: int = 10) -> list[Memory]: ...
    async def store(self, memory: Memory) -> str: ...
    async def search(self, query: str) -> list[Memory]: ...
    async def forget(self, memory_id: str) -> bool: ...
    async def all(self) -> list[Memory]: ...


@runtime_checkable
class HookRunner(Protocol):
    async def run(self, event: str, **kwargs: Any) -> HookResult: ...


# ── Helpers ──────────────────────────────────────────────────────────

def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
