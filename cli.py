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
    flags = {"memory": False, "no_memory": False, "provider": None, "permission_mode": None, "server": None, "client": None, "undo": False, "explain": False, "review": False}
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
            print("  koan                                    Interactive REPL")
            print('  koan "your prompt here"                 Single prompt')
            print("  koan --memory                           Enable memory mode")
            print("  koan --provider bedrock                 Override provider")
            print("  koan --server http://host:8000          Connect to enterprise server")
            print("  koan --server http://host:8000 --client name")
            print("  koan --undo                             Enable undo for file changes")
            print("  koan --explain                          Show reasoning after responses")
            print("  koan --review                           Peer review mode (coder + critic)")
            print("  koan config                             Show configuration")
            print("  koan memory                             Browse personal DB")
            print("  koan playbooks                          List learned playbooks")
            print("  koan sessions                           List past sessions")
            sys.exit(0)
        elif arg == "--memory":
            flags["memory"] = True
        elif arg == "--no-memory":
            flags["no_memory"] = True
        elif arg == "--undo":
            flags["undo"] = True
        elif arg == "--explain":
            flags["explain"] = True
        elif arg == "--review":
            flags["review"] = True
        elif arg == "--provider" and i + 1 < len(argv):
            i += 1
            flags["provider"] = argv[i]
        elif arg == "--server" and i + 1 < len(argv):
            i += 1
            flags["server"] = argv[i]
        elif arg == "--client" and i + 1 < len(argv):
            i += 1
            flags["client"] = argv[i]
        elif arg == "--permission-mode" and i + 1 < len(argv):
            i += 1
            flags["permission_mode"] = argv[i]
        elif not arg.startswith("-"):
            positional.append(arg)
        i += 1
    return flags, positional


def _build_provider(cfg, server_url=None, client_id=None):
    if server_url:
        from koan.providers.server import ServerProvider
        return ServerProvider(url=server_url, client_id=client_id or "default")

    from koan.providers.openai_compat import OpenAICompatProvider

    def _make_single_provider(name, pcfg):
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

    # Build primary provider
    primary_name = cfg.default_provider
    primary = _make_single_provider(primary_name, cfg.provider_config(primary_name))

    # Build fallback if configured
    fallback_name = cfg.fallback_provider
    if fallback_name and fallback_name != primary_name:
        from koan.providers.router import ProviderRouter, RoutingStrategy
        fallback = _make_single_provider(fallback_name, cfg.provider_config(fallback_name))
        strategy_str = cfg.get("provider", "routing_strategy", default="local_first")
        strategy = RoutingStrategy(strategy_str)
        return ProviderRouter(primary, fallback, strategy)

    return primary


async def _run_prompt(prompt, cfg, mode, server_url=None, client_id=None, review=False):
    from koan.loop import run_turn
    from koan.permissions import Permissions
    from koan.prompt import build_system_prompt
    from koan.render import Renderer
    from koan.session import Session
    from koan.tools.registry import discover_tools, get_registry
    from koan.types import PermissionLevel

    discover_tools()
    tools = get_registry()
    provider = _build_provider(cfg, server_url, client_id)
    session = Session(cfg.session_dir)
    renderer = Renderer()
    perms = Permissions(
        mode=PermissionLevel(cfg.permission_mode),
        rules=cfg.section("permissions").get("rules", {}),
    )

    # Memory mode setup
    memory_context = ""
    mem_store = None
    ep_store = None
    pb_store = None
    if mode.value == "memory":
        from koan.memory.recall import recall, format_memories_for_prompt
        from koan.memory.store import MemoryStore
        from koan.memory.episodic import EpisodicStore, format_episodes_for_prompt
        from koan.playbook.store import PlaybookStore
        from koan.playbook.matcher import match_playbook, format_playbook_offer, format_playbooks_for_prompt
        from koan.tools.memory_tools import set_memory_store
        mem_store = MemoryStore(cfg.memory_dir)
        ep_store = EpisodicStore(cfg.memory_dir)
        pb_store = PlaybookStore(cfg.memory_dir)
        set_memory_store(mem_store)
        memories = recall(mem_store, prompt, limit=cfg.get("memory", "max_recall_per_turn", default=10))
        memory_context = format_memories_for_prompt(memories)
        ep_context = format_episodes_for_prompt(ep_store.recent(3))
        pb_context = format_playbooks_for_prompt(pb_store.all())
        if ep_context:
            memory_context = memory_context + "\n\n" + ep_context if memory_context else ep_context
        if pb_context:
            memory_context = memory_context + "\n\n" + pb_context if memory_context else pb_context

    system_prompt = build_system_prompt(mode, tools, memory_context)

    def perm_check(name, inp):
        tool_def = tools.get(name)
        tp = tool_def.permission if tool_def else None
        return perms.check_with_prompt(name, inp, tp)

    mode_label = f"server → {server_url}" if server_url else f"{cfg.default_provider} | {cfg.permission_mode}"
    review_label = " | \033[33mreview\033[0m" if review else ""
    print(f"[{mode.value} mode | {mode_label}{review_label}]\n")

    collected_text = []
    def on_text_collect(text):
        collected_text.append(text)
        renderer.write(text)

    try:
        await run_turn(
            prompt,
            session=session,
            provider=provider,
            tools=tools,
            system_prompt=system_prompt,
            max_iterations=cfg.max_tool_iterations,
            permission_check=perm_check,
            on_text=on_text_collect,
        )

        # Peer review if enabled
        if review and collected_text:
            from koan.review import PeerReview
            reviewer = PeerReview(provider, max_rounds=3)
            initial = "".join(collected_text)
            result = await reviewer.run(
                prompt, initial, system_prompt,
                on_status=lambda s: sys.stdout.write(s) or sys.stdout.flush(),
            )
            if result["rounds"] > 0:
                renderer.write("\n" + result["final_response"])

    except Exception as exc:
        print(f"\nError: {exc}")

    renderer.newline()

    # Post-session consolidation in memory mode
    if mem_store and session.path.is_file():
        from koan.memory.consolidator import consolidate_session_with_episodes
        stats = consolidate_session_with_episodes(session.path, mem_store, ep_store, pb_store)
        parts = []
        if stats["stored"]:
            parts.append(f"+{stats['stored']} new")
        if stats["updated"]:
            parts.append(f"~{stats['updated']} updated")
        if stats["deleted"]:
            parts.append(f"-{stats['deleted']} removed")
        if stats.get("deduped"):
            parts.append(f"⊕{stats['deduped']} merged")
        if stats.get("episode"):
            parts.append("episode saved")
        if stats.get("playbooks_learned"):
            parts.append(f"{stats['playbooks_learned']} playbook(s) learned")
        if parts:
            print(f"\033[90m◇ Memory: {', '.join(parts)}\033[0m")

    print(f"\n[session: {session.session_id}]")


async def _run_repl(cfg, mode, server_url=None, client_id=None, review=False):
    from koan.loop import run_turn
    from koan.permissions import Permissions
    from koan.prompt import build_system_prompt
    from koan.render import Renderer
    from koan.session import Session
    from koan.tools.registry import discover_tools, get_registry
    from koan.types import PermissionLevel

    discover_tools()
    tools = get_registry()
    provider = _build_provider(cfg, server_url, client_id)
    session = Session(cfg.session_dir)
    renderer = Renderer()
    perms = Permissions(
        mode=PermissionLevel(cfg.permission_mode),
        rules=cfg.section("permissions").get("rules", {}),
    )

    # Memory mode setup
    mem_store = None
    ep_store = None
    pb_store = None
    if mode.value == "memory":
        from koan.memory.store import MemoryStore
        from koan.memory.episodic import EpisodicStore
        from koan.playbook.store import PlaybookStore
        from koan.tools.memory_tools import set_memory_store
        mem_store = MemoryStore(cfg.memory_dir)
        ep_store = EpisodicStore(cfg.memory_dir)
        pb_store = PlaybookStore(cfg.memory_dir)
        set_memory_store(mem_store)

    def perm_check(name, inp):
        tool_def = tools.get(name)
        tp = tool_def.permission if tool_def else None
        return perms.check_with_prompt(name, inp, tp)

    mem_label = f" | {mem_store.count()} memories" if mem_store else ""
    if server_url:
        print(f"Kōan v{__version__} — server mode | {server_url} | client: {client_id or 'default'}{mem_label}")
    else:
        from koan.compact import estimate_tokens, DEFAULT_COMPACT_THRESHOLD
        from koan.ui import banner, tip
        est = estimate_tokens(session.messages)
        pct = min(100, int(est / DEFAULT_COMPACT_THRESHOLD * 100))
        print(banner(
            mode=mode.value,
            provider=cfg.default_provider,
            memory_count=mem_store.count() if mem_store else 0,
            playbook_count=pb_store.count() if pb_store else 0,
            episode_count=ep_store.count() if ep_store else 0,
            review=review,
        ))
        print(tip())
        print()
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
            print("  /quit      Exit")
            print("  /config    Show config")
            print("  /mode      Show current mode")
            print("  /session   Show session info")
            print("  /context   Show context window usage")
            print("  /undo      Undo last file change (--undo)")
            print("  /why       Show reasoning (--explain)")
            print("  /sessions  List past sessions")
            print("  /memory    Show memories" if mem_store else "")
            print("  /playbooks Show learned playbooks" if pb_store else "")
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
        if user_input == "/context":
            from koan.compact import estimate_tokens, DEFAULT_COMPACT_THRESHOLD
            est = estimate_tokens(session.messages)
            pct = min(100, int(est / DEFAULT_COMPACT_THRESHOLD * 100))
            bar_len = 30
            filled = int(bar_len * pct / 100)
            bar = "█" * filled + "░" * (bar_len - filled)
            color = "\033[32m" if pct < 60 else "\033[33m" if pct < 80 else "\033[31m"
            print(f"  Context: {color}{bar} {pct}%\033[0m ({est:,} / {DEFAULT_COMPACT_THRESHOLD:,} tokens)")
            print(f"  Messages: {len(session.messages)}")
            if pct >= 80:
                print(f"  \033[33m⚠ High usage — auto-compaction will trigger soon\033[0m")
            print()
            continue
        if user_input == "/undo":
            from koan.undo import undo_manager
            result = undo_manager.undo()
            print(f"  {result}")
            print()
            continue
        if user_input == "/undo history":
            from koan.undo import undo_manager
            history = undo_manager.history()
            if not history:
                print("  No undo history.")
            else:
                for h in history[:10]:
                    print(f"  {h['action']:10} {h['path']:30} {h['ago']}")
            print()
            continue
        if user_input == "/why":
            from koan.explain import explain_tracker
            explanation = explain_tracker.format_explanation()
            if explanation:
                print(explanation)
            else:
                print("  \033[90mNo reasoning data. Use --explain flag to enable.\033[0m")
            print()
            continue
        if user_input == "/memory" and mem_store:
            print(f"Memories: {mem_store.count()}")
            for m in mem_store.all()[:10]:
                print(f"  [{m.type.value}] {m.content[:80]}")
            if mem_store.count() > 10:
                print(f"  ... and {mem_store.count() - 10} more")
            print()
            continue
        if user_input == "/sessions":
            from koan.session_control import list_sessions, format_session_list
            print(format_session_list(list_sessions(cfg.session_dir)))
            print()
            continue
        if user_input == "/playbooks" and pb_store:
            if pb_store.count() == 0:
                print("No playbooks learned yet.")
            else:
                print(f"Playbooks ({pb_store.count()}):")
                for pb in pb_store.all():
                    print(f"  {pb.summary()}")
            print()
            continue

        # Recall memories for this turn
        memory_context = ""
        if mem_store:
            from koan.memory.recall import recall, format_memories_for_prompt
            from koan.memory.episodic import format_episodes_for_prompt
            from koan.playbook.matcher import format_playbooks_for_prompt
            memories = recall(mem_store, user_input, limit=cfg.get("memory", "max_recall_per_turn", default=10))
            memory_context = format_memories_for_prompt(memories)

            # Show recall visual
            if memories:
                from koan.ui import memory_recall_box
                mem_dicts = [{"type": m.type.value, "content": m.content} for m in memories]
                ep_summaries = [e.summary for e in ep_store.recent(2)] if ep_store else []
                pb_names = [p.name for p in pb_store.all()[:2]] if pb_store else []
                print(memory_recall_box(mem_dicts, ep_summaries, pb_names))

            if ep_store:
                ep_context = format_episodes_for_prompt(ep_store.recent(3))
                if ep_context:
                    memory_context = memory_context + "\n\n" + ep_context if memory_context else ep_context
            if pb_store:
                pb_context = format_playbooks_for_prompt(pb_store.all())
                if pb_context:
                    memory_context = memory_context + "\n\n" + pb_context if memory_context else pb_context

        system_prompt = build_system_prompt(mode, tools, memory_context)

        print()
        try:
            await run_turn(
                user_input,
                session=session,
                provider=provider,
                tools=tools,
                system_prompt=system_prompt,
                max_iterations=cfg.max_tool_iterations,
                permission_check=perm_check,
                on_text=renderer.write,
            )
        except Exception as exc:
            print(f"\nError: {exc}")
        renderer.newline()

        # Status bar after each turn
        from koan.compact import estimate_tokens, DEFAULT_COMPACT_THRESHOLD
        from koan.ui import status_bar
        est = estimate_tokens(session.messages)
        pct = min(100, int(est / DEFAULT_COMPACT_THRESHOLD * 100))
        cost = session.cumulative_tokens * 0.000003 + session.cumulative_tokens * 0.000015  # rough estimate
        print(status_bar(
            tokens=session.cumulative_tokens,
            context_pct=pct,
            tools_used=sum(1 for m in session.messages for b in m.blocks if b.type == "tool_use"),
            memory_on=mem_store is not None,
            cost=cost,
        ))
        print()

    # Post-session consolidation
    if mem_store and session.path.is_file():
        from koan.memory.consolidator import consolidate_session_with_episodes
        stats = consolidate_session_with_episodes(session.path, mem_store, ep_store, pb_store)
        parts = []
        if stats["stored"]:
            parts.append(f"+{stats['stored']} new")
        if stats["updated"]:
            parts.append(f"~{stats['updated']} updated")
        if stats["deleted"]:
            parts.append(f"-{stats['deleted']} removed")
        if stats.get("deduped"):
            parts.append(f"⊕{stats['deduped']} merged")
        if stats.get("episode"):
            parts.append("episode saved")
        if stats.get("playbooks_learned"):
            parts.append(f"{stats['playbooks_learned']} playbook(s) learned")
        if parts:
            print(f"\033[90m◇ Memory: {', '.join(parts)}\033[0m")

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

    # Init logging
    from koan.log import setup_logging
    setup_logging()

    # Init optional features
    if flags["undo"]:
        from koan.undo import undo_manager
        undo_manager.__init__(enabled=True)
    if flags["explain"]:
        from koan.explain import explain_tracker
        explain_tracker.__init__(enabled=True)

    # Cleanup old sessions (>30 days)
    from koan.session_control import cleanup_old_sessions
    cleaned = cleanup_old_sessions(cfg.session_dir)
    if cleaned:
        from koan.log import get_logger
        get_logger("cli").info("Cleaned %d old sessions", cleaned)

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
        from koan.playbook.store import PlaybookStore
        pb_store = PlaybookStore(cfg.memory_dir)
        if pb_store.count() == 0:
            print("No playbooks learned yet. Use --memory mode to build up workflows.")
        else:
            print(f"Learned playbooks ({pb_store.count()}):\n")
            for pb in pb_store.all():
                print(f"  {pb.summary()}")
        return
    if cmd == "sessions":
        from koan.session_control import list_sessions, format_session_list, export_session
        rest = positional[1:]
        if rest and rest[0] == "export" and len(rest) > 1:
            session_path = cfg.session_dir / f"{rest[1]}.jsonl"
            print(export_session(session_path))
        else:
            sessions = list_sessions(cfg.session_dir)
            print(format_session_list(sessions))
        return

    # Load plugins
    plugin_dirs = cfg.get("plugins", "directories", default=["~/.koan/plugins", ".koan/plugins"])
    if isinstance(plugin_dirs, list):
        from koan.plugins.loader import discover_plugins
        loaded = discover_plugins(plugin_dirs)
        if loaded:
            print(f"\033[90m◇ Plugins: {', '.join(loaded)}\033[0m")

    if positional:
        asyncio.run(_run_prompt(" ".join(positional), cfg, mode, flags["server"], flags["client"], flags["review"]))
    else:
        asyncio.run(_run_repl(cfg, mode, flags["server"], flags["client"], flags["review"]))


if __name__ == "__main__":
    main()
