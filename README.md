# LangGraph Routine Maintenance Agent

Public-safe portfolio implementation of a scheduled, report-only repository
maintenance agent built with LangGraph and OpenRouter-backed tool-using agents.

Batch 3 is complete. The project now includes a repo-scoped safe tool registry,
OpenRouter chat-completions client, structured repo inspector contracts, bounded
configured command execution, and a sequential LangGraph workflow with a
deterministic no-LLM demo mode. Reports receive minimum secret redaction before
local writes. Later batches will polish report sections/redaction metadata,
Discord delivery, parallel fan-out, and systemd scheduling.

## Safety Model

- This repository is intended to be public.
- Do not commit real `.env` values, webhook URLs, API keys, private repo paths,
  raw logs, generated private reports, or proprietary snippets.
- The agent will only inspect repositories explicitly listed in its config.
- Each repo inspector run is constrained to the repo currently being inspected.
- LLM agents will call constrained Python tools; they will not receive
  unrestricted shell or filesystem access.
- Safe file tools skip symlinks, prune sensitive directories, and bound file
  reads before data can reach the model or report.
- Safe commands are opt-in per repo, parsed with `shlex.split`, and executed
  with `shell=False` from the configured repo root. They must also match a
  narrow report-only diagnostic profile.
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

## Safe Commands

`safe_commands` are configured per repo and only run when a matching
command-style check is enabled. A configured command label by itself is not
enough to execute. The deterministic mapping is:

- `tests` check -> `safe_commands.tests`
- `lint` check -> `safe_commands.lint`
- `build` check -> `safe_commands.build`
- `python-syntax` check -> `safe_commands.python-syntax`

Example:

```yaml
repos:
  - name: example-python-service
    path: /path/to/example-python-service
    enabled: true
    checks:
      - tests
    safe_commands:
      tests: python -m pytest --version
    timeout_seconds: 300
```

Commands are parsed into argv and run with `shell=False`, so shell features such
as pipes, redirection, variable expansion, and compound commands are not
supported in this batch. Stdout and stderr are bounded and redacted before they
enter tool results, workflow state, or reports. Unknown labels do not execute.

Allowed command profiles are intentionally narrow:

- `tests`: `pytest ...` or `python -m pytest ...`
- `lint`: `ruff check ...` without fix flags
- `python-syntax`: `python -m compileall ...` or `python -m py_compile ...`
- `build`: `python -m build ...`

Commands such as `python -c`, package-manager scripts, formatters, fix flags,
git mutation commands, and ad hoc file writes are rejected during config
validation. Command caches and temporary directories are redirected outside the
target repo where supported. Reports include only command results produced by
actual command tool calls.

## Agent Tools

Repo inspector agents can call only registered tools that accept `repo_name`.
They cannot pass arbitrary filesystem roots or shell commands, and model tool
calls for a different repo are rejected. Available tools include `git_status`,
`latest_commit`, `list_files`, `read_safe_file`, `search_static_markers`,
`detect_dependency_manifests`, and `run_configured_safe_command`.

## Source Of Truth

`PRD.md` is the main implementation reference and checklist. Update it whenever
scope, architecture, behavior, safety rules, or phase status changes.

## License

License selection is pending and must be finalized before public release.
