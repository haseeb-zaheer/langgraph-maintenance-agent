# LangGraph Routine Maintenance Agent

Report-only repository maintenance reviews powered by LangGraph, constrained
local tools, and optional OpenRouter-backed agents. The default public demo runs
without credentials against a committed synthetic fixture repository.

## Quickstart

Install `uv`, clone this repository, then run:

```bash
uv sync
uv run pytest
uv run langgraph-maintenance validate-config examples/repos.yaml
uv run langgraph-maintenance run --config examples/repos.yaml --no-llm --dry-run
```

The demo config points to `examples/fixture-repo/`. Relative repo paths in a
config file resolve from that config file's directory, so the example works from
any fresh clone location.

`--dry-run` performs checks and renders report content in memory, but does not
write report files or send Discord messages.

## Safety Model

- The agent only inspects repositories explicitly listed in its config.
- It is report-only: no fixes, formatting, upgrades, commits, resets, cleanup,
  or deletes are performed in target repositories.
- LLM agents call constrained Python tools; they do not receive unrestricted
  shell or filesystem access.
- Safe file tools skip symlinks, prune sensitive/generated paths, bound reads,
  and redact output before content reaches model state or reports.
- Safe commands are opt-in per repo, parsed with `shlex.split`, executed with
  `shell=False`, and limited to narrow diagnostic profiles.
- Discord delivery is disabled by default and uses webhook URLs from environment
  variables only.

## LLM Mode

OpenRouter-backed inspection is optional. Set credentials locally, then run with
`--llm`:

```bash
export OPENROUTER_API_KEY="sk-or-placeholder"
export LANGGRAPH_MAINTENANCE_LLM_MODEL="deepseek/deepseek-v4-flash"
uv run langgraph-maintenance run \
  --config examples/repos.yaml \
  --llm \
  --provider openrouter \
  --max-concurrency 4
```

In LLM mode, repository inspectors must gather evidence with registered tools
before final structured findings are accepted. Semantic source-code review is
available only in LLM mode; `--no-llm` reports those checks as skipped instead
of inventing findings.

## Discord Delivery

Discord delivery is opt-in. Set a webhook in your environment, then enable it in
config with `report.discord_enabled: true` or force one run with
`--send-discord`.

```bash
export LANGGRAPH_MAINTENANCE_DISCORD_WEBHOOK_URL="<discord webhook url>"
uv run langgraph-maintenance run \
  --config examples/repos.yaml \
  --no-llm \
  --send-discord \
  --summary-only
uv run langgraph-maintenance send reports/latest.md --summary-only
```

Use `--no-discord` to suppress config-based delivery. Long reports are split
into numbered webhook messages below Discord's 2,000-character `content` limit.

## Configure Repositories

Create a YAML config with explicit repo entries:

```yaml
repos:
  - name: example-python-service
    path: ../example-python-service
    enabled: true
    required: false
    checks:
      - git-status
      - docs
      - static-search
      - dependency-metadata
    safe_commands: {}
    source_roots:
      - src
      - tests
    timeout_seconds: 300

report:
  output_dir: reports
  filename_prefix: routine-maintenance
  update_latest: true
  discord_enabled: false
```

Use absolute paths or paths relative to the config file location. Do not commit
private repo paths, tokens, webhook URLs, raw logs, or generated private reports.

## Safe Commands

`safe_commands` run only when the matching check is enabled:

- `tests` check -> `safe_commands.tests`
- `lint` check -> `safe_commands.lint`
- `build` check -> `safe_commands.build`
- `python-syntax` check -> `safe_commands.python-syntax`

Example:

```yaml
repos:
  - name: example-python-service
    path: ../example-python-service
    enabled: true
    checks:
      - tests
    safe_commands:
      tests: python -m pytest --version
```

Allowed command profiles are intentionally narrow:

- `tests`: `pytest ...` or `python -m pytest ...`
- `lint`: `ruff check ...` without fix flags
- `python-syntax`: `python -m compileall ...` or `python -m py_compile ...`
- `build`: `python -m build ...`

Commands such as `python -c`, package-manager scripts, formatters, fix flags,
git mutation commands, and ad hoc file writes are rejected during config
validation.

## Source Review Budgets

Source review reads are bounded by config:

```yaml
source_roots:
  - src
  - tests
source_review_max_plan_files: 12
source_review_max_files: 20
source_review_max_bytes_per_file: 12000
source_review_max_total_bytes: 80000
```

The workflow maps candidates, validates an LLM-created review plan, batch-reads
only approved planned files, and rejects source findings that cite unread files.

## Optional Linux Scheduling

The primary public path is the manual CLI above. Linux users can optionally
install user-level systemd units:

```bash
scripts/install_systemd_user_units.sh
```

The helper writes units under `~/.config/systemd/user/` with the current clone
path, reloads user systemd, and enables the timer. The timer runs daily at
11:00 AM local system time.

Manual wrapper scripts are also available:

```bash
LANGGRAPH_MAINTENANCE_CONFIG=examples/repos.yaml scripts/run_maintenance_check.sh
LANGGRAPH_MAINTENANCE_CONFIG=examples/repos.yaml scripts/run_and_send.sh
```

The scripts load local `.env` if present, default to `--no-llm`, use
`LANGGRAPH_MAINTENANCE_TIMEOUT_SECONDS=3600`, and avoid sending stale Discord
reports after failures.

macOS and Windows users can run the CLI manually or use their operating
system's scheduler.

## Development And Validation

```bash
uv sync
uv run pytest
uv run ruff check .
uv run mypy src
uv build
uv run langgraph-maintenance --help
bash -n scripts/run_maintenance_check.sh scripts/run_and_send.sh scripts/install_systemd_user_units.sh
```

Generated reports are ignored except for `reports/.gitkeep`. Fatal
config/runtime failures write fresh timestamped failure reports and do not
replace or send stale `reports/latest.md`.

## Source Of Truth

`PRD.md` is the main implementation reference and launch checklist. Update it
whenever scope, architecture, behavior, safety rules, docs, packaging,
scheduling, or validation status changes.

## License

MIT. See `LICENSE`.
