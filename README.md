# LangGraph Routine Maintenance Agent

Public-safe portfolio implementation of a scheduled, report-only repository
maintenance agent built with LangGraph.

The project is currently in Batch 1 implementation. Batch 1 builds the Python
package foundation, configuration validation, typed schemas, and reusable
runtime helpers. Repository scanning, Discord delivery, systemd scheduling, safe
command execution, and LLM summarization are intentionally later phases.

## Safety Model

- This repository is intended to be public.
- Do not commit real `.env` values, webhook URLs, API keys, private repo paths,
  raw logs, generated private reports, or proprietary snippets.
- The agent will only scan repositories explicitly listed in its config.
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

Batch 1 currently provides config validation, typed schemas, and runtime helper
tests. End-to-end repository inspection starts in a later phase.

## Source Of Truth

`PRD.md` is the main implementation reference and checklist. Update it whenever
scope, architecture, behavior, safety rules, or phase status changes.

## License

License selection is pending and must be finalized before public release.
