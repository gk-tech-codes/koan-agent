# Kōan

A personal AI agent that learns your workflows and gets better every session.

## What Makes Kōan Different

- **Three-layer memory** — learns your preferences, remembers past sessions, and extracts reusable workflow playbooks
- **Peer review mode** — two agents: one codes, one critiques. Code survives adversarial review before you see it
- **Deferred consolidation** — memory extraction runs after the session, zero overhead during your work
- **Local-first** — your data stays on your machine. No cloud storage of personal knowledge
- **Undo system** — every file change is backed up. One command to revert

## Quick Start

```bash
pip install httpx boto3

# With AWS Bedrock
python cli.py --provider bedrock

# With Ollama (local, free)
brew install ollama && ollama pull qwen2.5-coder:14b
python cli.py

# Memory mode — agent learns about you
python cli.py --memory --provider bedrock

# Peer review mode — adversarial code generation
python cli.py --review --provider bedrock

# All features
python cli.py --memory --review --undo --explain --provider bedrock
```

## Features

### Core
- Streaming conversation loop with tool execution
- 5 built-in tools: bash, read_file, write_file, edit_file, glob_search, grep_search
- Multi-provider: Ollama, AWS Bedrock, OpenAI, any OpenAI-compatible endpoint
- Provider router with automatic fallback
- Configurable permission system (read_only, workspace_write, full_access)
- Plugin system with 8 hook points
- Auto-compaction when context exceeds threshold

### Memory (--memory)
- **Semantic** — preferences, facts, lessons, instructions
- **Episodic** — compressed session summaries
- **Procedural** — learned multi-step workflow playbooks
- Post-session consolidation with importance scoring
- Memory deduplication and time-based decay

### Peer Review (--review)
- GAN-style adversarial code generation
- Coder agent writes, Critic agent reviews
- Iterates until Critic approves or max rounds reached
- Catches security issues, missing error handling, code quality problems

### UX
- Branded terminal UI with session stats
- Colored markdown rendering (headers, code blocks, lists, inline code)
- Diff preview before file writes
- Compact tool output (line counts, file sizes)
- Context window usage indicator
- Status bar with token count and cost estimate
- Memory recall visualization

### Optional Flags
- `--undo` — backup files before changes, `/undo` to revert
- `--explain` — track reasoning, `/why` to see which memories influenced decisions
- `--review` — peer review mode
- `--memory` — enable three-layer memory
- `--server URL` — connect to enterprise server instead of LLM directly

## REPL Commands

```
/help       Show commands
/config     Show configuration
/mode       Show current mode
/session    Show session info
/context    Show context window usage with progress bar
/memory     Browse stored memories
/playbooks  Show learned playbooks
/sessions   List past sessions
/undo       Revert last file change (--undo)
/why        Show reasoning (--explain)
/quit       Exit
```

## Configuration

Default config in `config.default.toml`. Override with:
- `~/.koan/config.toml` — user-level
- `.koan/config.toml` — project-level
- Environment variables
- CLI flags

## Project Structure

```
koan/
├── loop.py              # Core conversation loop
├── session.py           # JSONL session persistence
├── compact.py           # Auto-compaction
├── config.py            # 5-layer config merge
├── types.py             # Protocols, enums, dataclasses
├── permissions.py       # Permission system
├── render.py            # Colored terminal output
├── ui.py                # Banner, status bar, recall box
├── diff.py              # Diff preview for file changes
├── review.py            # GAN-style peer review
├── undo.py              # File change undo system
├── explain.py           # Reasoning tracker
├── prompt.py            # System prompt builder
├── spinner.py           # Thinking indicators
├── log.py               # Structured logging
├── errors.py            # Error hierarchy
├── memory/
│   ├── store.py         # JSONL memory database
│   ├── semantic.py      # Preferences, facts, lessons
│   ├── episodic.py      # Session summaries
│   ├── consolidator.py  # Post-session extraction
│   ├── scorer.py        # Importance scoring
│   ├── recall.py        # Memory retrieval
│   └── decay.py         # Confidence decay
├── playbook/
│   ├── store.py         # Playbook storage
│   ├── extractor.py     # Session → playbook extraction
│   └── matcher.py       # Intent → playbook matching
├── providers/
│   ├── base.py          # Provider interface
│   ├── openai_compat.py # Ollama / OpenAI / vLLM
│   ├── bedrock.py       # AWS Bedrock
│   ├── router.py        # Multi-provider fallback
│   └── server.py        # Enterprise server mode
├── tools/
│   ├── registry.py      # @tool decorator + auto-schema
│   ├── bash.py          # Shell execution
│   ├── files.py         # File operations + edit
│   └── memory_tools.py  # Memory recall/store/forget
└── plugins/
    ├── hooks.py         # @hook decorator + dispatch
    └── loader.py        # Plugin auto-discovery
```

## Research

Published paper: [Kōan: Deferred Consolidation and Tripartite Memory for Self-Improving Personal CLI Agents](https://www.researchgate.net/publication/403911716)

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.
