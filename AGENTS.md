# LangGraph Routine Maintenance Agent Instructions

## Project Purpose

This project is a public portfolio implementation of a scheduled, report-only
repository maintenance agent built with LangGraph.

The agent will inspect an explicit allowlist of local repositories, run only
configured read-only checks, generate structured Markdown reports, and send safe
summaries to Discord or another configured reporting destination.

## Public Repository Safety

This repository is intended to be public.

Never commit secrets, private `.env` values, access tokens, webhook URLs, API
keys, private repository paths that are not already public-safe, raw logs,
non-public runtime data, user data, non-public service URLs, or closed-source
snippets from scanned repositories.

Use placeholders in documentation and examples:

- `DISCORD_WEBHOOK_URL=...`
- `/path/to/example-repo`
- `OPENAI_API_KEY=...`

Before committing, check staged changes for sensitive material. Prefer
redacted examples and synthetic sample reports.

## Operating Rules

- The agent must be report-only unless a user explicitly starts a separate
  implementation workflow.
- For maintenance scans and source-code review, prefer LLM-backed agentic runs
  by default. Use `--llm`/OpenRouter-backed inspection unless the user
  explicitly asks for `--no-llm`, credentials are unavailable, or the task is a
  test/public-demo path that intentionally verifies deterministic fallback.
- Do not treat no-LLM mode as equivalent to agentic review. In no-LLM mode,
  semantic source-code review must be reported as skipped or incomplete rather
  than simulated.
- Source-review depth is governed by configured source budgets and validated
  plans, not by a low global tool-call cap. Keep `max_tool_calls` as an
  emergency guard for generic tool loops and runaway behavior.
- Only scan repositories explicitly configured in the project config.
- Do not infer or crawl every sibling directory under a repositories folder.
- Preserve dirty worktrees in target repositories. Report dirty state; do not
  clean it.
- Do not run fix commands, formatters, codemods, dependency upgrades,
  migrations, destructive cleanup, git reset, git checkout, or commits in
  target repositories.
- Only run commands listed as safe for the target repository.
- Never print or send secret values to Discord, logs, reports, tests, fixtures,
  or screenshots.
- Keep reports actionable and grouped by severity.
- Treat each configured repository as a separate project with its own docs,
  commands, generated files, and git history.

## Required Project Docs

Keep these files up to date whenever project scope, architecture, safety rules,
configuration, scheduling, or report behavior changes:

- `AGENTS.md`
- `ARCHITECTURE.md`
- `README.md`

## Intended Structure

- `src/langgraph_maintenance_agent/`: application package.
- `config/`: example allowlist and check definitions.
- `reports/`: generated local reports, ignored except sample fixtures.
- `scripts/`: manual and scheduled entrypoints.
- `systemd/`: optional user service and timer units.
- `tests/`: unit, integration, and safety tests.
- `examples/`: public-safe sample configs and reports.
- `docs/`: architecture notes and portfolio writeups.

## LangGraph Design Intent

Use LangGraph for the supervisor workflow and state transitions. The intended
portfolio design is agentic: OpenRouter-backed LLM agents inspect repositories
by calling constrained Python tools such as git status, safe file listing,
safe file reads, static marker search, dependency manifest detection, and
configured safe-command execution.

Keep deterministic logic in normal Python functions for config validation, tool
safety, sensitive path blocking, command execution mechanics, redaction, report
rendering, and delivery.

Prefer typed state and structured outputs. Make safety boundaries explicit in
code, tests, prompts, and config validation.
