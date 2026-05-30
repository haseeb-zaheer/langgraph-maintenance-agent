# LangGraph Routine Maintenance Agent

Public-safe portfolio implementation of a scheduled, report-only repository
maintenance agent built with LangGraph and OpenRouter-backed tool-using agents.

Batch 2 is complete. The project now includes a repo-scoped safe tool registry,
OpenRouter chat-completions client, structured repo inspector contracts, and a
sequential LangGraph workflow with a deterministic no-LLM demo mode. Later
batches will polish report rendering/redaction, Discord delivery, safe command
execution, parallel fan-out, and systemd scheduling.

## Safety Model

- This repository is intended to be public.
- Do not commit real `.env` values, webhook URLs, API keys, private repo paths,
  raw logs, generated private reports, or proprietary snippets.
- The agent will only inspect repositories explicitly listed in its config.
- LLM agents will call constrained Python tools; they will not receive
  unrestricted shell or filesystem access.
- The agent is report-only and must not fix, format, upgrade, commit, reset,
  clean, or delete files in target repositories.

## Development

```bash
uv run pytest
uv run ruff check .
uv run mypy src
uv run langgraph-maintenance --help
```

Validate the public-safe example config:

```bash
uv run langgraph-maintenance validate-config examples/repos.yaml
```

Run the public-safe dry-run demo without credentials:

```bash
uv run langgraph-maintenance run --config examples/repos.yaml --no-llm --dry-run
```

Run with OpenRouter-backed tool-using repo inspectors:

```bash
export OPENROUTER_API_KEY="sk-or-placeholder"
export LANGGRAPH_MAINTENANCE_LLM_MODEL="openrouter/model-placeholder"
uv run langgraph-maintenance run --config examples/repos.yaml --llm --provider openrouter
```

`--dry-run` performs checks and renders report content in memory, but it does
not write report files or send Discord messages.

## Agent Tools

Repo inspector agents can call only registered tools that accept `repo_name`.
They cannot pass arbitrary filesystem roots or shell commands. Available tools
include `git_status`, `latest_commit`, `list_files`, `read_safe_file`,
`search_static_markers`, `detect_dependency_manifests`, and a skipped
`run_configured_safe_command` stub reserved for the command-execution batch.

## Source Of Truth

`PRD.md` is the main implementation reference and checklist. Update it whenever
scope, architecture, behavior, safety rules, or phase status changes.

## License

License selection is pending and must be finalized before public release.
