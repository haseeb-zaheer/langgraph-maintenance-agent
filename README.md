# LangGraph Routine Maintenance Agent

Public-safe portfolio implementation of a scheduled, report-only repository
maintenance agent built with LangGraph and OpenRouter-backed tool-using agents.

Phases 10, 11, 13, and 14 are complete. The project includes a repo-scoped safe tool
registry, OpenRouter chat-completions client, structured repo inspector and
summary contracts, bounded configured command execution, polished redacted
Markdown reports, fresh failure reports, parallel LangGraph fan-out/fan-in, and
bounded staged source-code review tools for LLM-backed bug/refactor/test-gap
suggestions. Optional Discord webhook delivery runs through local scripts and
user-level systemd units.

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
- Source review maps approved candidates, validates an LLM review plan, then
  batch-reads only planned Python and JavaScript/TypeScript source files from
  approved source roots. Generated artifacts such as `.next/`, source maps,
  dependency folders, build output, and caches are excluded.
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
export LANGGRAPH_MAINTENANCE_LLM_MODEL="deepseek/deepseek-v4-flash"
uv run langgraph-maintenance run --config examples/repos.yaml --llm --provider openrouter --max-concurrency 4
```

LLM mode requires evidence before final structured findings are accepted.
For source review, the deterministic workflow maps the source tree, exposes
ranked candidates, validates a model-created review plan, batch-reads only
planned files, and rejects findings that cite unread source files.
Semantic source-code review requires LLM mode; `--no-llm` reports source review
as skipped instead of inventing findings.

`--dry-run` performs checks and renders report content in memory, but it does
not write report files or send Discord messages.

Reports are written to a date-based Markdown file and copied to
`reports/latest.md` on successful non-dry runs. Fatal config/runtime failures
write a fresh timestamped failure report and do not replace or send stale
`latest.md`.

Discord delivery is opt-in and disabled by default. Set a webhook in the
environment, then enable it in config with `report.discord_enabled: true` or
force a single run with `--send-discord`. Use `--no-discord` to suppress config
delivery. Long reports are split into numbered webhook messages below
Discord's 2,000-character `content` limit.

```bash
export LANGGRAPH_MAINTENANCE_DISCORD_WEBHOOK_URL="<discord webhook url>"
uv run langgraph-maintenance run --config examples/repos.yaml --no-llm --send-discord --summary-only
uv run langgraph-maintenance send reports/latest.md --summary-only
```

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
`latest_commit`, `list_files`, `read_safe_file`, `summarize_source_tree`,
`list_source_files`, `read_source_file`, `read_source_files`, `search_static_markers`,
`detect_dependency_manifests`, and `run_configured_safe_command`.

## Source Review

Enable LLM-backed source review with one or more source checks:

```yaml
repos:
  - name: example-python-service
    path: /path/to/example-python-service
    enabled: true
    checks:
      - source-review
      - bug-risk-review
      - refactor-review
      - test-gap-review
    source_roots:
      - src
      - tests
    source_review_max_plan_files: 12
    source_review_max_files: 20
    source_review_max_bytes_per_file: 12000
    source_review_max_total_bytes: 80000
```

The first source-review scope is Python plus Next.js/JavaScript/TypeScript.
Candidate ranking prioritizes Next.js API routes, route handlers, auth,
rate-limit, request/response, environment, network, filesystem, sitemap,
robots, and runtime glue files. Reports include a `Source Review Coverage`
section with candidate, planned, read, skipped, generated-skip, byte, mode, and
plan-rationale metadata. Reports cite concise evidence paths and suggested
human actions, never raw source dumps. The agent still never edits target
repositories.

## Scheduled Runtime

Manual wrapper run without Discord:

```bash
LANGGRAPH_MAINTENANCE_CONFIG=examples/repos.yaml scripts/run_maintenance_check.sh
```

Manual wrapper run with Discord delivery after a successful fresh report:

```bash
LANGGRAPH_MAINTENANCE_CONFIG=examples/repos.yaml scripts/run_and_send.sh
```

The scripts load local `.env` if present, default to `--no-llm`, use
`LANGGRAPH_MAINTENANCE_TIMEOUT_SECONDS=3600`, and use
`LANGGRAPH_MAINTENANCE_MAX_CONCURRENCY=4`. Set
`LANGGRAPH_MAINTENANCE_USE_LLM=1` to use OpenRouter-backed repo inspectors.

Install the user-level systemd timer:

```bash
mkdir -p ~/.config/systemd/user
cp systemd/langgraph-maintenance-agent.service ~/.config/systemd/user/
cp systemd/langgraph-maintenance-agent.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now langgraph-maintenance-agent.timer
systemctl --user list-timers langgraph-maintenance-agent.timer
```

The timer runs daily at 11:00 AM local system time. Failed script runs write a
fresh failure report and do not send stale `reports/latest.md`.

## Source Of Truth

`PRD.md` is the main implementation reference and checklist. Update it whenever
scope, architecture, behavior, safety rules, or phase status changes.

## License

License selection is pending and must be finalized before public release.
