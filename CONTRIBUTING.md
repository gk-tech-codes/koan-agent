# Contributing to Kōan

## Rules

### Never commit without explicit approval
- Do NOT commit or push unless the user explicitly asks
- Always show `git status` and let the user review before committing
- Never force push

### Never hardcode secrets
- No API keys, tokens, ARNs, or credentials in code
- All secrets come from environment variables or config files
- Config files with secrets must be in `.gitignore`

### Files that must NEVER be committed
- `.env`, `.env.*` — environment files with secrets
- `~/.koan/` — runtime data (sessions, memories)
- `*.pem`, `*.key` — certificates and keys
- `~/.aws/credentials` — AWS credentials
- Any file containing API keys, tokens, or passwords

### Files that stay local only (in .gitignore)
- `DESIGN.md` — internal design document
- `PHASES.md` — development phases plan
- `THESIS.md` — research thesis
- Agent-generated test files (games, demos, etc.)

### Before any git operation
1. Run `git status` and review
2. Run `git diff --cached` to check staged content
3. Grep for secrets: `grep -r "AKIA\|aws_secret\|api_key=\|token=" --include="*.py" --include="*.toml"`
4. Only proceed if the user confirms

### Code standards
- All components implement a Protocol from `types.py`
- Configuration goes in `config.default.toml`, never hardcoded
- Every new feature gets a test in `tests/`
- Follow the phased development plan — don't skip phases
- Keep the conversation loop (`loop.py`) under 200 lines

### Branching
- `main` — stable, working code only
- Feature branches for new phases: `phase-3-memory`, `phase-5-playbooks`, etc.
- PR review before merging to main
