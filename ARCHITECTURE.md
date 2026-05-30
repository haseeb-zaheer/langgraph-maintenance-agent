# LangGraph Routine Maintenance Agent Architecture

## Overview

The project is a workflow-first LangGraph application with OpenRouter-backed
tool-using agents. Deterministic Python code handles configuration, validation,
tool safety, redaction, report rendering, and delivery mechanics. LLM agents
reason over repositories by calling constrained Python tools.

## Target Flow

```text
systemd timer / manual CLI
  -> Python CLI
    -> LangGraph supervisor workflow
      -> load + validate config
      -> prepare run context
      -> select enabled repos
      -> fan out repo inspector agents
        -> safe repository tools
        -> structured findings
      -> merge findings
      -> redact sensitive output
      -> render Markdown report
      -> write local report
      -> send Discord summary
```

## Current Implementation

The current implementation includes the tool-using agent workflow, parallel
LangGraph repo fan-out/fan-in, bounded configured command execution, polished
reporting, redaction metadata, fresh failure reports, local runtime scripts,
optional user-level systemd templates, bounded LLM-backed source-code review,
and optional Discord delivery:

- `tools/` exposes repo-scoped read-only tools and OpenRouter-compatible tool
  schemas.
- `llm/openrouter.py` provides a direct non-streaming Chat Completions client
  with tool-call parsing and JSON-schema response format support.
- `agents/repo_inspector.py` runs an OpenRouter-backed tool loop or a
  deterministic no-LLM fallback. In no-LLM mode, configured command-style
  checks map to `safe_commands` labels for `tests`, `lint`, `build`, and
  `python-syntax`. In LLM mode, final structured repo output is accepted only
  after required evidence tools for configured checks have completed.
- `tools/commands.py` executes only commands explicitly configured for the
  current repo. Commands are parsed with `shlex.split`, run with `shell=False`,
  restricted to approved diagnostic profiles, use the configured repo path as
  `cwd`, redirect supported temp/cache paths outside the repo, enforce
  `timeout_seconds` or a 300-second default, and return bounded redacted
  stdout/stderr excerpts.
- `tools/source.py` exposes bounded source-code review tools for Python and
  JavaScript/TypeScript repositories. The source tools summarize source roots,
  list review candidates, and read individual approved source files while
  enforcing sensitive/generated path blocking, per-file limits, per-run budgets,
  symlink rejection, binary rejection, and redaction.
- `reporting/markdown.py` renders structured reports with executive summary,
  severity sections, repo scan/skipped summaries, source-review sections,
  dependency and command results, dirty worktree notes, next actions, and
  per-repo appendix.
- `reporting/redaction.py` redacts common secrets and returns aggregate
  metadata so reports can warn that redaction occurred without exposing values.
- `reporting/discord.py` sends redacted report content or compact summaries to
  Discord webhooks loaded only from environment variables. Long messages are
  split below Discord's 2,000-character `content` limit and prefixed with
  chunk numbers.
- `graph.py` assembles the supervisor workflow:
  `load_config -> prepare_run -> select_repos -> inspect_repo_branch fan-out ->
  normalize_agent_output -> merge_results ->
  redact_structured_state -> summarize_with_agent -> render_markdown ->
  redact_report -> write_report -> send_discord_summary`.
- LangGraph `Send` starts one `inspect_repo_branch` per enabled repo. Each
  branch builds a one-repo `ToolRegistry`, so tool schemas expose only that
  repo name and tool access remains isolated. Branch outputs are aggregated and
  fan-in sorts results by config order before reporting.
- `--max-concurrency` and `run_workflow(max_concurrency=...)` pass LangGraph
  runtime concurrency limits. The default is `4`.
- Non-required repo branch exceptions become repo-scoped recoverable errors.
  Required repo failures are detected after fan-in and fail the run before
  report write/delivery, causing a fresh failure report instead of stale
  `latest.md`.
- Fatal workflow failures write a fresh timestamped failure report and do not
  update `reports/latest.md`.
- `scripts/run_maintenance_check.sh` runs a local check without Discord.
  `scripts/run_and_send.sh` sends only after a successful fresh run. Both load
  `.env` without printing values, default to no-LLM mode, enforce
  `LANGGRAPH_MAINTENANCE_TIMEOUT_SECONDS`, and write script-level failure
  reports on timeout or wrapper failure.
- `systemd/langgraph-maintenance-agent.service` is a template rendered by
  `scripts/install_systemd_user_units.sh` for optional Linux user scheduling.
  The timer runs daily at 11:00 AM local system time.

## Remaining Boundary

Later batches still own optional temp/cache isolation for commands that need
writable caches and post-launch polish.

## Agent Safety Boundary

Repo inspector agents do not receive raw shell access. They call a registry of
constrained tools such as `git_status`, `list_files`, `read_safe_file`,
`summarize_source_tree`, `list_source_files`, `read_source_file`,
`search_static_markers`, `detect_dependency_manifests`, and
`run_configured_safe_command`. Tools resolve repo names through validated
config, block sensitive paths, bound outputs, and redact before content is
stored or sent back to the model. File traversal skips symlinks and prunes
blocked runtime, generated, or dependency directories. Each inspector run
rejects model tool calls or final structured output that tries to switch to a
different configured repository.

Source-review checks require source tree summary, source file listing, and at
least one source file read before final LLM findings are accepted. The no-LLM
fallback collects bounded source metadata but records semantic source review as
skipped because deterministic tooling does not reason about code behavior.

`run_configured_safe_command` is a deterministic safety-boundary tool rather
than raw shell access. The model can supply only `repo_name` and
`command_label`; the actual command string comes from validated config for that
repo, and the label must also be enabled by the repo's configured checks.
Unknown or disabled labels return safe tool errors without execution. Timed-out
commands return a successful tool envelope with a timed-out `CommandResult` and
an incomplete reason. Nonzero exits are preserved as command results and
normalized into findings by the inspector/reporting path. In LLM mode, reported
command results come only from actual command tool calls, not final model JSON.

## Documentation

This architecture document should stay aligned with `README.md` and
`AGENTS.md` when behavior, structure, safety rules, or scheduling changes.
