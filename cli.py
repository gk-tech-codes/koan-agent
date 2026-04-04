"""Kōan CLI — entrypoint for the personal AI agent."""

from __future__ import annotations

import asyncio
import os
import sys

from koan import __version__
from koan.config import load_config
from koan.types import Mode


def _print_config(cfg):
    print(f"Mode:       {cfg.mode}")
    print(f"Provider:   {cfg.default_provider}")
    print(f"Fallback:   {cfg.fallback_provider or '(none)'}")
    print(f"Permission: {cfg.permission_mode}")
    print(f"Memory:     {'on' if cfg.memory_enabled else 'off'}")
    print(f"Sessions:   {cfg.session_dir}")
    if cfg.sources:
        print(f"Loaded from: {', '.join(cfg.sources)}")


def _parse_args(argv):
    flags = {"memory": False, "no_memory": False, "provider": None, "permission_mode": None}
    positional = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--version", "-v"):
            print(f"koan {__version__}")
            sys.exit(0)
        elif arg in ("--help", "-h"):
            print(f"koan {__version__} — A personal AI agent that learns your workflows.\n")
            print("Usage:")
            print("  koan                          Interactive REPL")
            print('  koan "your prompt here"       Single prompt')
            print("  koan --memory                 Enable memory mode")
            print("  koan --provider bedrock       Override provider")
            print("  koan config                   Show configuration")
            print("  koan memory                   Browse personal DB")
            print("  koan playbooks                List learned playbooks")
            print("  koan sessions                 List past sessions")
            sys.exit(0)
        elif arg == "--memory":
            flags["memory"] = True
        elif arg == "--no-memory":
            flags["no_memory"] = True
        elif arg == "--provider" and i + 1 < len(argv):
            i += 1
            flags["provider"] = argv[i]
        elif arg == "--permission-mode" and i + 1 < len(argv):
            i += 1
            flags["permission_mode"] = argv[i]
        elif not arg.startswith("-"):
            positional.append(arg)
        i += 1
    return flags, positional


def _build_provider(cfg):
    from koan.providers.openai_compat import OpenAICompatProvider

    name = cfg.default_provider
    pcfg = cfg.provider_config(name)
    ptype = pcfg.get("type", "openai_compat")

    if ptype == "openai_compat":
        api_key = pcfg.get("api_key", "")
        if not api_key and name == "openai":
            api_key = os.environ.get("OPENAI_API_KEY", "")
        return OpenAICompatProvider(
            name=name,
            endpoint=pcfg.get("endpoint", "http://localhost:11434/v1/chat/completions"),
            model=pcfg.get("model", "qwen2.5-coder:14b"),
            api_key=api_key,
        )
    elif ptype == "anthropic":
        api_key = pcfg.get("api_key", os.environ.get("ANTHROPIC_API_KEY", ""))
        return OpenAICompatProvider(
            name=name,
            endpoint=pcfg.get("endpoint", "https://api.anthropic.com/v1/messages"),
            model=pcfg.get("model", "claude-sonnet-4-20250514"),
            api_key=api_key,
        )
    elif ptype == "bedrock":
        from koan.providers.bedrock import BedrockProvider
        return BedrockProvider(
            name=name,
            model=pcfg.get("model", "us.anthropic.claude-sonnet-4-20250514-v1:0"),
            region=pcfg.get("region", os.environ.get("AWS_REGION", "us-east-1")),
            role_arn=pcfg.get("role_arn", os.environ.get("BEDROCK_ROLE_ARN", "")),
            profile=pcfg.get("profile", os.environ.get("AWS_PROFILE", "")),
        )

    raise ValueError(f"Unknown provider type: {ptype}")


async def _run_prompt(prompt, cfg, mode):
    from koan.loop import run_turn
    from koan.prompt import build_system_prompt
    from koan.render import Renderer
    from koan.session import Session
    from koan.tools.registry import discover_tools, get_registry

    discover_tools()
    tools = get_registry()
    provider = _build_provider(cfg)
    session = Session(cfg.session_dir)
    system_prompt = build_system_prompt(mode, tools)
    renderer = Renderer()

    print(f"[{mode.value} mode | {cfg.default_provider} | {provider._model}]\n")

    try:
        await run_turn(
            prompt,
            session=session,
            provider=provider,
            tools=tools,
            system_prompt=system_prompt,
            max_iterations=cfg.max_tool_iterations,
            on_text=renderer.write,
        )
    except Exception as exc:
        print(f"\nError: {exc}")

    renderer.newline()
    print(f"\n[session: {session.session_id}]")


async def _run_repl(cfg, mode):
    from koan.loop import run_turn
    from koan.prompt import build_system_prompt
    from koan.render import Renderer
    from koan.session import Session
    from koan.tools.registry import discover_tools, get_registry

    discover_tools()
    tools = get_registry()
    provider = _build_provider(cfg)
    session = Session(cfg.session_dir)
    system_prompt = build_system_prompt(mode, tools)
    renderer = Renderer()

    print(f"Kōan v{__version__} — {mode.value} mode | {cfg.default_provider} | {provider._model}")
    print("Type /help for commands, /quit to exit.\n")

    while True:
        try:
            user_input = input("you: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input:
            continue
        if user_input in ("/quit", "/exit", "/q"):
            break
        if user_input == "/help":
            print("  /quit     Exit")
            print("  /config   Show config")
            print("  /mode     Show current mode")
            print("  /session  Show session info")
            print()
            continue
        if user_input == "/config":
            _print_config(cfg)
            continue
        if user_input == "/mode":
            print(f"Current mode: {mode.value}")
            continue
        if user_input == "/session":
            print(f"Session: {session.session_id}")
            print(f"Messages: {len(session.messages)}")
            print(f"Tokens: ~{session.cumulative_tokens}")
            continue

        print()
        try:
            await run_turn(
                user_input,
                session=session,
                provider=provider,
                tools=tools,
                system_prompt=system_prompt,
                max_iterations=cfg.max_tool_iterations,
                on_text=renderer.write,
            )
        except Exception as exc:
            print(f"\nError: {exc}")
        renderer.newline()
        print()

    print(f"[session: {session.session_id}]")
    print("Goodbye.")


def main():
    flags, positional = _parse_args(sys.argv[1:])

    overrides = {}
    if flags["memory"]:
        overrides.setdefault("memory", {})["enabled"] = True
        overrides.setdefault("agent", {})["mode"] = "memory"
    if flags["no_memory"]:
        overrides.setdefault("memory", {})["enabled"] = False
        overrides.setdefault("agent", {})["mode"] = "session"
    if flags["provider"]:
        overrides.setdefault("provider", {})["default"] = flags["provider"]
    if flags["permission_mode"]:
        overrides.setdefault("permissions", {})["mode"] = flags["permission_mode"]

    cfg = load_config(cli_overrides=overrides or None)
    mode = Mode.MEMORY if cfg.memory_enabled else Mode.SESSION

    cmd = positional[0] if positional else None

    if cmd == "config":
        rest = positional[1:]
        if rest:
            print(f"{rest[0]} = {cfg.get(*rest[0].split('.'))}")
        else:
            _print_config(cfg)
        return
    if cmd == "memory":
        print("[memory]  (Phase 3)")
        return
    if cmd == "playbooks":
        print("[playbooks]  (Phase 5)")
        return
    if cmd == "sessions":
        print("[sessions]  (Phase 1 — list not yet implemented)")
        return

    if positional:
        asyncio.run(_run_prompt(" ".join(positional), cfg, mode))
    else:
        asyncio.run(_run_repl(cfg, mode))


if __name__ == "__main__":
    main()
