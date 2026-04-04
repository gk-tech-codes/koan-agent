"""Bash tool — execute shell commands.

Adapted from claw-code bash.rs: timeout, output truncation, error handling.
"""

from __future__ import annotations

import asyncio
import os

from koan.tools.registry import tool

_MAX_OUTPUT = 50_000  # truncate output beyond this


@tool(name="bash", description="Execute a shell command", permission="exec")
async def bash(command: str, timeout: int = 30) -> str:
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=os.getcwd(),
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return f"[timed out after {timeout}s]"

    out = stdout.decode(errors="replace") if stdout else ""
    err = stderr.decode(errors="replace") if stderr else ""

    if len(out) > _MAX_OUTPUT:
        out = out[:_MAX_OUTPUT] + f"\n[truncated — {len(out)} chars total]"

    if proc.returncode != 0:
        result = f"Exit code: {proc.returncode}\n"
        if out:
            result += f"stdout:\n{out}\n"
        if err:
            result += f"stderr:\n{err}"
        return result.strip()

    return out.strip() if out else "(no output)"
