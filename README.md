# Kōan

A personal AI agent that learns your workflows and gets better every session.

## What is this

Kōan is a CLI-based AI coding agent with a unique three-layer memory system:
- **Semantic memory** — learns your preferences, facts, and coding patterns
- **Episodic memory** — remembers what happened in past sessions
- **Procedural memory** — learns multi-step workflows as reusable playbooks

The agent runs locally, stores everything as inspectable JSONL files, and works with local LLMs (Ollama) or cloud providers (AWS Bedrock, OpenAI, Anthropic).

## Quick Start

```bash
# Install dependencies
pip install httpx boto3

# Run with AWS Bedrock
export BEDROCK_ROLE_ARN="your-role-arn"
python cli.py --provider bedrock "list files in this directory"

# Run with Ollama (local, free)
brew install ollama && ollama pull qwen2.5-coder:14b
python cli.py "list files in this directory"

# Interactive REPL
python cli.py --provider bedrock
```

## Usage

```bash
# Single prompt
python cli.py "your prompt here"

# Interactive REPL
python cli.py

# Override provider
python cli.py --provider bedrock
python cli.py --provider ollama
python cli.py --provider openai

# Memory mode (Phase 3+)
python cli.py --memory "your prompt"

# Subcommands
python cli.py config              # Show configuration
python cli.py memory              # Browse personal DB (Phase 3+)
python cli.py playbooks           # List learned playbooks (Phase 5+)
python cli.py sessions            # List past sessions
```

## REPL Commands

```
/help      Show commands
/config    Show current configuration
/mode      Show current mode
/session   Show session info
/quit      Exit
```

## Configuration

Default config is in `config.default.toml`. Override with:
- `~/.koan/config.toml` — user-level config
- `.koan/config.toml` — project-level config
- Environment variables (`BEDROCK_ROLE_ARN`, `OPENAI_API_KEY`, etc.)
- CLI flags (`--provider`, `--memory`, `--permission-mode`)

## Providers

| Provider | Type | Config key |
|---|---|---|
| Ollama | Local (free) | `ollama` |
| AWS Bedrock | Cloud | `bedrock` |
| OpenAI | Cloud | `openai` |
| Anthropic | Cloud | `anthropic` |

## Tools

Built-in tools available to the agent:
- `bash` — execute shell commands
- `read_file` — read file contents
- `write_file` — write/create files
- `glob_search` — find files by pattern
- `grep_search` — search file contents

## Project Structure

```
koan/
├── __init__.py          # Version
├── types.py             # Protocols, enums, dataclasses
├── errors.py            # Error hierarchy
├── config.py            # TOML config loader (3-layer merge)
├── loop.py              # Core conversation loop
├── session.py           # JSONL session persistence
├── prompt.py            # System prompt builder
├── render.py            # Terminal output rendering
├── spinner.py           # Thinking/tool spinners
├── providers/
│   ├── base.py          # Provider interface
│   ├── openai_compat.py # Ollama / OpenAI / vLLM
│   └── bedrock.py       # AWS Bedrock
├── tools/
│   ├── registry.py      # @tool decorator + auto-discovery
│   ├── bash.py          # Shell execution
│   └── files.py         # File operations
├── memory/              # Phase 3+
├── playbook/            # Phase 5+
└── plugins/             # Phase 6+
```

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.
