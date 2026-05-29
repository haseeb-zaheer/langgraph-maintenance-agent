# LangGraph Routine Maintenance Agent PRD

## Summary

Build a public portfolio-quality LangGraph application that performs scheduled,
report-only maintenance reviews over an explicit allowlist of local
repositories.

The agent should inspect repository health, dependency metadata, configured
lint/test/build commands, documentation drift, dirty worktrees, and suspicious
maintenance risks. It must never modify target repositories. It should write a
local Markdown report and send a redacted summary to Discord.

This project is a production-style rebuild of a Codex CLI prototype, but it
should stand on its own as a conventional Python/LangGraph repository suitable
for public review.

## Portfolio Goals

- Demonstrate a real agentic workflow beyond a chatbot.
- Show LangGraph state-machine design with explicit nodes, routing, fan-out, and
  merge behavior.
- Show practical safety engineering for local tool use.
- Show structured outputs, schema validation, and redaction.
- Show scheduled automation with clear failure handling.
- Show tests for guardrails, config validation, report formatting, and workflow
  behavior.
- Keep all examples and fixtures public-safe.

## Non-Goals

- No autonomous fixes.
- No dependency upgrades.
- No code formatting or codemods in target repositories.
- No commits in target repositories.
- No implicit scanning of all local repositories.
- No uploading private reports to public services.
- No storing secret values in reports, fixtures, logs, screenshots, or commits.
- No web dashboard for the MVP unless the CLI workflow is already complete.

## Primary User Stories

- As a developer, I can configure a small allowlist of repositories and receive
  a daily maintenance summary.
- As a developer, I can run the agent manually from the CLI before enabling the
  scheduler.
- As a developer, I can see which checks ran, which checks were skipped, and why.
- As a developer, I can trust that dirty worktrees and local secrets are
  preserved.
- As a portfolio reviewer, I can understand the architecture, safety model, and
  test coverage without needing private credentials.

## MVP Definition

The core MVP is complete when:

- A CLI can run the LangGraph workflow against a public-safe sample config.
- The workflow scans only enabled configured repositories.
- The workflow performs read-only metadata/docs/static checks.
- Findings are normalized into typed records with severity.
- The final local Markdown report is generated.
- Secret redaction is applied before report persistence.
- Unit tests and at least one workflow smoke test pass.
- Documentation explains setup, safety, architecture, and portfolio value.

The release-ready MVP additionally includes:

- The workflow can optionally run explicitly configured safe commands.
- Discord delivery works through an environment variable webhook.
- Secret redaction is applied before report delivery.
- Wrapper scripts and systemd units are documented.

## Target Architecture

The project should be workflow-first, with LangGraph coordinating explicit
state transitions and normal Python handling deterministic work. LLM calls
should be used only where judgment, summarization, or prioritization adds value.

```text
systemd timer / manual CLI
  -> Python CLI
    -> LangGraph workflow
      -> load + validate config
      -> prepare run context
      -> fan out repo inspections
      -> run read-only checks
      -> run configured safe commands
      -> classify + normalize findings
      -> merge findings
      -> redact sensitive output
      -> render Markdown report
      -> write local report
      -> send Discord summary
```

### Proposed Package Layout

```text
src/langgraph_maintenance_agent/
  cli.py
  config.py
  graph.py
  state.py
  schemas.py

  checks/
    git.py
    docs.py
    static.py
    dependencies.py
    commands.py

  reporting/
    markdown.py
    discord.py
    redaction.py

  llm/
    prompts.py
    summarizer.py

  runtime/
    paths.py
    logging.py
    errors.py
```

### Deterministic Logic Vs LLM Logic

Use deterministic Python for:

- Config loading and validation.
- Repository allowlist enforcement.
- Git metadata collection.
- Static file/path scanning.
- Safe command execution.
- Timeout handling.
- Secret redaction.
- Markdown rendering.
- Discord delivery.
- Failure report generation.

Use the LLM for:

- Executive-summary generation.
- Finding deduplication assistance when deterministic keys are insufficient.
- Suggested next actions.
- Ambiguous risk explanation.
- Human-readable prioritization from already structured findings.

Do not make every check an LLM agent. The portfolio value should come from a
clear production-style workflow with explicit safety boundaries, typed state,
and selective model use.

### LangGraph Node Design

The primary graph should include these nodes:

- `load_config`: read and validate the allowlist config.
- `prepare_run`: create run id, timestamps, report paths, and output dirs.
- `select_repos`: filter enabled repositories.
- `inspect_repo`: run per-repo deterministic metadata, docs, dependency, and
  static checks.
- `run_safe_commands`: run explicitly configured commands with timeouts.
- `classify_findings`: convert raw results into typed severity-ranked findings.
- `merge_results`: deduplicate and group findings across repositories.
- `summarize_with_llm`: optional summary and next-action generation.
- `redact_report`: remove secrets and unsafe values before persistence/delivery.
- `render_markdown`: produce the full local Markdown report.
- `write_report`: write timestamped report and update `reports/latest.md`.
- `send_discord_summary`: send a safe summary or chunks to Discord.
- `handle_failure`: write and send a fresh failure report on workflow failure.

### Execution Model

The MVP may run repository checks sequentially. The portfolio-ready version
should add LangGraph fan-out/fan-in:

```text
select_repos
  -> inspect_repo(repo A)
  -> inspect_repo(repo B)
  -> inspect_repo(repo N)
  -> merge_results
```

The workflow should continue when one repository fails unless the config marks
that repository as required. Failures should become findings or incomplete-check
records instead of crashing the entire run when possible.

### Typed State Shape

The graph state should be serializable and testable. A representative shape:

```python
class AgentState(TypedDict):
    run_id: str
    started_at: str
    config_path: str
    repos: list[RepoConfig]
    repo_results: list[RepoResult]
    findings: list[Finding]
    skipped_checks: list[SkippedCheck]
    report_markdown: str | None
    report_path: str | None
    discord_status: DeliveryStatus | None
    errors: list[AgentError]
```

The concrete implementation can use `TypedDict`, Pydantic models, or a mixture,
but external data such as config, findings, command results, and delivery status
should be schema-validated.

### Safety Boundary

The safety boundary must be enforced in code, not only prompts:

- Config allowlist only.
- Safe command allowlist only.
- Command timeouts.
- Blocked unsafe command keywords.
- No `.env` reads from target repositories.
- No raw private log reads.
- Redaction before report persistence and delivery.
- Generated reports ignored by git.
- Synthetic public-safe examples only.
- Fresh failure reports instead of stale `latest.md` reuse.

## Architecture Checklist

### Repository Scaffold

- [ ] Initialize Python project metadata with `pyproject.toml`.
- [ ] Choose import package name: `langgraph_maintenance_agent`.
- [x] Create `src/langgraph_maintenance_agent/`.
- [x] Create `tests/`.
- [x] Create `config/`.
- [x] Create `examples/`.
- [x] Create `reports/` with only `.gitkeep` committed.
- [x] Create `scripts/`.
- [x] Create `systemd/`.
- [x] Add `.gitignore` for `.env`, caches, generated reports, logs, and virtual
      environments.
- [x] Add `.env.example` with placeholders only.
- [ ] Add `README.md`.
- [ ] Add `ARCHITECTURE.md`.
- [ ] Add license decision before publishing.

### Core Dependencies

- [ ] Add LangGraph.
- [ ] Add LangChain/OpenAI integration only if needed for model calls.
- [ ] Add Pydantic for config and report schemas.
- [ ] Add PyYAML or equivalent for config loading.
- [ ] Add pytest.
- [ ] Add ruff or another linter.
- [ ] Add mypy or pyright if type checking is included.
- [ ] Keep dependency list minimal and explain each major dependency.

### Configuration Model

- [ ] Define config schema for repositories.
- [ ] Support fields: `name`, `path`, `enabled`, `checks`,
      `safe_commands`, `timeout_seconds`, `notes`.
- [ ] Support optional report settings.
- [ ] Support optional model settings through environment variables, not secrets
      in config files.
- [ ] Validate that repo paths are absolute or intentionally relative to a safe
      base directory.
- [ ] Reject duplicate repo names.
- [ ] Reject enabled repos without a path.
- [ ] Reject unknown check names unless explicitly allowed as custom checks.
- [ ] Reject unsafe command names such as `fix`, `format`, `upgrade`, `delete`,
      `reset`, `checkout`, `commit`, or `clean`.
- [ ] Provide `examples/repos.yaml` with synthetic public-safe paths.
- [ ] Never include real private webhook URLs or tokens in config.

### LangGraph State Design

- [ ] Define a typed graph state.
- [ ] Include run metadata: run id, start time, config path, output paths.
- [ ] Include repository configs.
- [ ] Include per-repo check results.
- [ ] Include findings.
- [ ] Include skipped checks.
- [ ] Include command execution summaries.
- [ ] Include redaction warnings.
- [ ] Include final report content.
- [ ] Include delivery status.
- [ ] Include fatal errors and partial failures.
- [ ] Ensure state is serializable for debugging and tests.

### Workflow Nodes

- [ ] `load_config`: read and validate allowlist config.
- [ ] `prepare_run`: create run id, output paths, and runtime context.
- [ ] `select_repos`: filter enabled repositories.
- [ ] `inspect_repo`: run repo-level read-only checks.
- [ ] `run_safe_commands`: execute configured commands with timeouts.
- [ ] `detect_stack`: identify Python, Node, Docker, dbt, or other stack hints.
- [ ] `scan_docs`: detect README, AGENTS, architecture docs, setup docs.
- [ ] `scan_static_markers`: find TODO/FIXME/HACK and suspicious artifacts.
- [ ] `classify_findings`: normalize severity and category.
- [ ] `merge_results`: dedupe and group findings.
- [ ] `redact_report`: remove secret patterns and unsafe values.
- [ ] `render_markdown`: create the local full report.
- [ ] `write_report`: persist report and latest pointer/copy.
- [ ] `send_discord_summary`: send safe summary or full chunks based on settings.
- [ ] `handle_failure`: write a fresh failure report if the workflow fails.

### Graph Routing

- [ ] Fan out enabled repositories for parallel inspection when supported.
- [ ] Continue if one repository fails, unless config marks it required.
- [ ] Route command timeouts to skipped/incomplete check records.
- [ ] Route redaction hits to a warning section without exposing values.
- [ ] Route fatal configuration errors to a local failure report.
- [ ] Ensure failed runs never send stale previous reports.

### Tooling And Command Execution

- [ ] Implement a command runner wrapper.
- [ ] Enforce working directory per target repo.
- [ ] Enforce timeout per command.
- [ ] Capture exit status.
- [ ] Capture bounded stdout/stderr excerpts.
- [ ] Redact command output before storing it in findings.
- [ ] Avoid shell invocation unless necessary.
- [ ] Support shell commands only when explicitly configured.
- [ ] Mark commands as skipped if not configured.
- [ ] Avoid reading `.env`, raw logs, credential files, private key files, and
      other sensitive files.
- [ ] Add tests for unsafe command rejection.

### Repository Checks

- [ ] Check path existence.
- [ ] Check whether path is a git repository.
- [ ] Record branch.
- [ ] Record concise dirty state.
- [ ] Record ahead/behind state when available.
- [ ] Record latest commit hash/date/subject.
- [ ] Detect untracked files without printing sensitive contents.
- [ ] Detect docs presence.
- [ ] Detect dependency manifests and lockfiles.
- [ ] Detect test/lint/build command availability only through config.
- [ ] Search TODO/FIXME/HACK markers.
- [ ] Search suspicious committed artifacts by filename pattern.
- [ ] Record skipped checks and reasons.

### LLM Usage

- [ ] Decide where LLM calls are genuinely useful.
- [ ] Use deterministic Python for config parsing, command execution, redaction,
      and report writing where possible.
- [ ] Use LLM for summarizing findings and suggesting next actions.
- [ ] Require structured output from LLM summarization.
- [ ] Add prompt templates under `src/.../prompts/` or `prompts/`.
- [ ] Keep prompts public-safe and free of private examples.
- [ ] Add tests or golden fixtures for prompt inputs/outputs where practical.
- [ ] Support a no-LLM dry run mode for tests and demos.

### Report Format

- [ ] Generate `reports/YYYY-MM-DD-routine-maintenance.md`.
- [ ] Generate a timestamped filename if the date report already exists.
- [ ] Update `reports/latest.md`.
- [ ] Include executive summary.
- [ ] Include critical findings.
- [ ] Include high priority findings.
- [ ] Include medium priority findings.
- [ ] Include low priority findings.
- [ ] Include repositories scanned.
- [ ] Include repositories skipped.
- [ ] Include dependency concerns.
- [ ] Include test/lint/build results.
- [ ] Include dirty worktrees.
- [ ] Include suggested next actions.
- [ ] Include appendix with per-repo details.
- [ ] Include commands run and exit statuses.
- [ ] Include skipped checks and reasons.
- [ ] Include auditor failures or incomplete checks.
- [ ] Use `None found.` for empty severity sections.

### Discord Delivery

- [ ] Load webhook from environment only.
- [ ] Support `.env` locally without committing it.
- [ ] Prefer a routine-specific env var such as
      `LANGGRAPH_MAINTENANCE_DISCORD_WEBHOOK_URL`.
- [ ] Support optional fallback `DISCORD_WEBHOOK_URL`.
- [ ] Redact report before sending.
- [ ] Extract a short summary for Discord.
- [ ] Split long messages safely below Discord limits.
- [ ] Handle HTTP failures clearly.
- [ ] Never print the webhook URL.
- [ ] Add `--summary-only` option.
- [ ] Add tests for chunking and redaction.

### Scheduling

- [ ] Provide manual CLI command.
- [ ] Provide `scripts/run_maintenance_check.sh`.
- [ ] Provide `scripts/run_and_send.sh`.
- [ ] Provide `systemd/langgraph-maintenance-agent.service`.
- [ ] Provide `systemd/langgraph-maintenance-agent.timer`.
- [ ] Schedule daily at 11:00 AM local system time.
- [ ] Document user-level systemd installation.
- [ ] Ensure failed runs write and send a fresh failure report.
- [ ] Add timeout environment variable for the whole run.

### Security And Public-Safety Checklist

- [ ] `.env` is ignored.
- [ ] Generated reports are ignored by default.
- [ ] Raw event logs are ignored.
- [ ] Test fixtures contain only synthetic data.
- [ ] Example configs use fake paths and placeholders.
- [ ] Redaction covers common secret names.
- [ ] Redaction covers Discord webhook URL patterns.
- [ ] Redaction covers authorization headers.
- [ ] Redaction covers private key block markers.
- [ ] Docs warn that this repo is public.
- [ ] Pre-commit or documented manual checks scan for common secrets.
- [ ] No private repository-specific findings are committed.

### Testing Checklist

- [ ] Config validation tests.
- [ ] Unsafe command rejection tests.
- [ ] Command runner timeout tests.
- [ ] Redaction tests.
- [ ] Discord chunking tests.
- [ ] Markdown rendering tests.
- [ ] Git metadata parser tests.
- [ ] Static marker scanner tests.
- [ ] Workflow smoke test with temporary synthetic git repos.
- [ ] Failure path test that prevents stale report sending.
- [ ] No-LLM mode test.
- [ ] CLI argument parsing tests.
- [ ] Public fixture safety test.

### Observability

- [ ] Log run id.
- [ ] Log report path.
- [ ] Log repositories scanned/skipped.
- [ ] Log command names and exit statuses without sensitive output.
- [ ] Optionally write a JSON run summary.
- [ ] Optionally write LangGraph state snapshots with redaction.
- [ ] Document where local logs live.

### CLI Requirements

- [ ] `langgraph-maintenance run --config config/repos.yaml`.
- [ ] `langgraph-maintenance send reports/latest.md`.
- [ ] `langgraph-maintenance validate-config config/repos.yaml`.
- [ ] `langgraph-maintenance render-sample-report`.
- [ ] Support `--summary-only`.
- [ ] Support `--dry-run`.
- [ ] Support `--no-llm`.
- [ ] Support configurable output directory.

### Documentation Checklist

- [ ] `README.md` explains the problem, design, and demo workflow.
- [ ] `ARCHITECTURE.md` includes graph diagram and node descriptions.
- [ ] `docs/safety.md` explains guardrails and public-repo boundaries.
- [ ] `docs/portfolio-notes.md` explains what this demonstrates.
- [ ] `examples/repos.yaml` is public-safe.
- [ ] `examples/sample-report.md` is synthetic.
- [ ] Document manual run.
- [ ] Document Discord setup with placeholders.
- [ ] Document systemd timer setup.
- [ ] Document tests and local development.

### Portfolio Presentation Checklist

- [ ] Add a concise project pitch to README.
- [ ] Include architecture diagram.
- [ ] Include screenshots or copied sample output using synthetic data.
- [ ] Explain why LangGraph fits the problem.
- [ ] Highlight safety decisions.
- [ ] Highlight structured outputs and tests.
- [ ] Highlight how the project avoids autonomous mutation.
- [ ] Add future work section.

## Implementation Phases And Tracking

This section is the authoritative work tracker for future implementation
sessions. Complete phases in order unless a later phase explicitly says it can
be done independently.

Status legend:

- `[ ]` not started
- `[~]` partially done
- `[x]` complete
- `[!]` blocked or needs a decision

### Current Repository State

- [x] Git repository initialized on branch `main`.
- [x] Public-safety `AGENTS.md` exists and states that the repository is intended
      to be public.
- [x] `PRD.md` exists with target architecture and implementation phases.
- [x] Placeholder directories exist for `src/`, `tests/`, `config/`,
      `examples/`, `reports/`, `scripts/`, and `systemd/`.
- [x] `.gitignore` ignores local env files, caches, generated reports, logs, and
      common Python build artifacts.
- [x] `.env.example` exists with placeholder environment variables only.
- [ ] No Python package metadata exists yet.
- [ ] No application code exists yet.
- [ ] No tests exist yet.
- [ ] No README, architecture doc, examples, or sample reports exist yet.

### Phase 1: Project Foundation And Public-Safe Scaffold

Goal: turn the documentation scaffold into a runnable Python project skeleton
without implementing the full agent yet.

Deliverables:

- [ ] Add `pyproject.toml`.
- [ ] Use package name `langgraph-maintenance-agent` for distribution metadata.
- [ ] Use import package `langgraph_maintenance_agent`.
- [ ] Set Python requirement to a modern stable version, preferably
      `>=3.11,<3.15` unless tooling requires otherwise.
- [ ] Add runtime dependencies:
      - `langgraph`
      - `pydantic`
      - `PyYAML` or another YAML parser
- [ ] Add optional LLM dependencies only if the implementation needs them in the
      same phase. Prefer delaying provider-specific packages until Phase 8.
- [ ] Add dev dependencies:
      - `pytest`
      - `ruff`
      - type checker if chosen, such as `mypy` or `pyright`
- [ ] Configure console script:
      `langgraph-maintenance = langgraph_maintenance_agent.cli:main`.
- [ ] Add package `__init__.py`.
- [ ] Add initial module files:
      - `cli.py`
      - `config.py`
      - `schemas.py`
      - `state.py`
      - `graph.py`
- [ ] Add subpackages with `__init__.py`:
      - `checks/`
      - `reporting/`
      - `runtime/`
      - `llm/`
- [ ] Add `README.md` with a concise public-safe project summary and current
      development status.
- [ ] Add `ARCHITECTURE.md` with the target architecture from this PRD.
- [ ] Add `docs/safety.md` describing public-repo safety, allowlist-only scans,
      secret redaction, and report-only behavior.
- [ ] Add `examples/repos.yaml` using synthetic paths only.
- [ ] Add `examples/sample-report.md` with synthetic findings only.
- [ ] Add a license file or explicitly document that license selection is
      pending before publication.

Implementation notes:

- Keep the first scaffold simple. Do not add Discord, systemd, safe command
  execution, or LLM calls in this phase.
- Do not include real local repository paths in public examples.
- Do not commit generated reports except synthetic examples under `examples/`.

Validation:

- [ ] `python -m pytest` runs, even if only smoke tests exist.
- [ ] `ruff check .` runs if ruff is configured.
- [ ] `langgraph-maintenance --help` works after editable install.
- [ ] `git status --short --ignored` shows no accidental secret/runtime files
      staged.

Exit criteria:

- [ ] A future session can install the project locally and run the empty CLI.
- [ ] Public-facing docs explain what the project is and what is not implemented
      yet.

### Phase 2: Config Schema And Validation

Goal: implement the configuration boundary before any repository scanning exists.
This is the main safety gate for the entire project.

Deliverables:

- [ ] Implement `RepoConfig` schema.
- [ ] Implement `CheckName` or equivalent constrained check representation.
- [ ] Implement `SafeCommand` schema.
- [ ] Implement top-level `AppConfig` schema.
- [ ] Support repo fields:
      - `name`
      - `path`
      - `enabled`
      - `checks`
      - `safe_commands`
      - `timeout_seconds`
      - `notes`
      - optional `required`
- [ ] Support report settings:
      - output directory
      - report filename prefix
      - whether to update `latest.md`
      - whether Discord delivery is enabled
- [ ] Support runtime settings through environment variables, not committed
      config secrets.
- [ ] Implement `load_config(path: Path) -> AppConfig`.
- [ ] Validate duplicate repo names are rejected.
- [ ] Validate enabled repos require a path.
- [ ] Validate unknown check names are rejected unless custom checks are
      explicitly supported later.
- [ ] Validate unsafe command labels are rejected, including names containing:
      `fix`, `format`, `upgrade`, `delete`, `remove`, `reset`, `checkout`,
      `commit`, `clean`, `migrate`, `install`.
- [ ] Validate unsafe command strings are rejected when they clearly contain
      destructive operations such as:
      `rm -rf`, `git reset`, `git checkout`, `git clean`, `npm audit fix`,
      `pip install -U`, `uv add`, `poetry add`, `alembic upgrade`.
- [ ] Decide and document whether shell command strings are allowed. Recommended:
      allow shell strings only for explicitly configured `safe_commands`, but
      run all built-in checks without shell where possible.
- [ ] Implement CLI command:
      `langgraph-maintenance validate-config examples/repos.yaml`.
- [ ] Add `examples/repos.yaml` that validates without requiring private paths.

Tests:

- [ ] Valid config loads successfully.
- [ ] Missing file produces a useful error.
- [ ] Duplicate repo names fail.
- [ ] Enabled repo without path fails.
- [ ] Unknown check fails.
- [ ] Unsafe safe-command label fails.
- [ ] Unsafe safe-command string fails.
- [ ] Disabled repo with incomplete details is handled according to documented
      behavior.
- [ ] Example config stays public-safe.

Validation:

- [ ] `langgraph-maintenance validate-config examples/repos.yaml` exits `0`.
- [ ] Invalid config fixtures exit nonzero or raise expected validation errors.

Exit criteria:

- [ ] No repository scanning can occur without passing config validation.

### Phase 3: Deterministic Schemas, Findings, And Runtime Utilities

Goal: define the typed data model used by checks, graph state, reporting, and
tests before wiring the graph.

Deliverables:

- [ ] Implement severity enum:
      - `critical`
      - `high`
      - `medium`
      - `low`
      - optional `info`
- [ ] Implement finding category enum:
      - `security`
      - `dependency`
      - `test`
      - `build`
      - `git`
      - `docs`
      - `static`
      - `runtime`
      - `configuration`
- [ ] Implement `Finding` schema with:
      - id or fingerprint
      - repo name
      - severity
      - category
      - title
      - description
      - evidence paths
      - command reference if applicable
      - suggested action
      - needs human review flag
- [ ] Implement `CommandResult` schema with:
      - command label
      - command string or argv
      - working directory
      - exit code
      - timed out flag
      - bounded stdout excerpt
      - bounded stderr excerpt
      - started/ended timestamps or duration
- [ ] Implement `SkippedCheck` schema.
- [ ] Implement `RepoResult` schema.
- [ ] Implement `DeliveryStatus` schema.
- [ ] Implement `AgentError` schema.
- [ ] Implement `AgentState` using `TypedDict` or Pydantic-compatible state.
- [ ] Implement deterministic finding fingerprinting for dedupe.
- [ ] Implement runtime path helpers for report names:
      `YYYY-MM-DD-routine-maintenance.md` and timestamp fallback.
- [ ] Implement bounded text helpers for command output excerpts.

Tests:

- [ ] Finding serialization round trip.
- [ ] Fingerprints are stable for equivalent findings.
- [ ] Fingerprints differ for meaningfully different findings.
- [ ] Command output excerpts are bounded.
- [ ] Report path helper avoids overwriting existing date report.
- [ ] Agent state can be serialized to JSON-safe structures.

Validation:

- [ ] Unit tests pass.
- [ ] Type checker passes if configured.

Exit criteria:

- [ ] Later phases can return structured results without inventing ad hoc
      dictionaries.

### Phase 4: Built-In Read-Only Repository Checks

Goal: implement the safe deterministic checks that do not execute project test,
lint, build, install, fix, or cleanup commands.

Deliverables:

- [ ] Implement repo path existence check.
- [ ] Implement git repository detection.
- [ ] Implement git branch detection.
- [ ] Implement latest commit metadata collection.
- [ ] Implement concise dirty-state summary.
- [ ] Implement ahead/behind summary when remote tracking info is available.
- [ ] Implement untracked file summary without reading file contents.
- [ ] Implement ignored runtime artifact summary where useful.
- [ ] Implement docs presence check:
      - `README.md`
      - `AGENTS.md`
      - `ARCHITECTURE.md`
      - `CONTRIBUTING.md`
      - project-specific setup docs
- [ ] Implement dependency manifest detection:
      - Python: `pyproject.toml`, `requirements*.txt`, `uv.lock`,
        `poetry.lock`
      - Node: `package.json`, lockfiles
      - Docker: `Dockerfile`, `compose.yaml`, `docker-compose.yml`
      - dbt: `dbt_project.yml`
- [ ] Implement static marker scan for TODO/FIXME/HACK.
- [ ] Implement suspicious artifact filename scan:
      `.env`, `.pem`, `.key`, `id_rsa`, `.sqlite`, `.db`, `.log`,
      generated report files, local caches.
- [ ] Ensure sensitive files are not read. Only report file paths or counts when
      safe.
- [ ] Convert check outcomes into `RepoResult`, `Finding`, and `SkippedCheck`
      structures.
- [ ] Add built-in check dispatcher for configured check names:
      - `git-status`
      - `docs`
      - `static-search`
      - `dependency-metadata`

Tests:

- [ ] Temporary non-git directory is reported correctly.
- [ ] Temporary git repo with clean state is reported correctly.
- [ ] Temporary git repo with dirty state is reported correctly.
- [ ] Docs presence detection works.
- [ ] Dependency manifest detection works for synthetic files.
- [ ] Static marker scan finds TODO/FIXME/HACK without reading ignored secrets.
- [ ] Suspicious artifact scan reports paths/counts without printing contents.
- [ ] Disabled checks are skipped with reasons.

Validation:

- [ ] Tests create only temporary synthetic repositories.
- [ ] No test fixture contains private paths or secrets.

Exit criteria:

- [ ] The project can inspect synthetic repos without LLMs, Discord, safe
      commands, or LangGraph.

### Phase 5: Markdown Reporting And Redaction

Goal: produce useful local reports from deterministic check results and ensure
secret redaction is available before anything is persisted or delivered.

Deliverables:

- [ ] Implement redaction patterns for:
      - Discord webhook URLs
      - common token/secret/password/api-key assignments
      - authorization headers
      - private key block markers
      - `.env`-style values
- [ ] Implement redaction result metadata, such as count of redactions by type.
- [ ] Implement Markdown renderer with required sections:
      - `# Routine Maintenance Report - YYYY-MM-DD`
      - `## Executive Summary`
      - `## Critical Findings`
      - `## High Priority`
      - `## Medium Priority`
      - `## Low Priority`
      - `## Repositories Scanned`
      - `## Repositories Skipped`
      - `## Dependency Concerns`
      - `## Test/Lint/Build Results`
      - `## Dirty Worktrees`
      - `## Suggested Next Actions`
      - `## Appendix: Per-Repo Details`
- [ ] Use `None found.` for empty severity sections.
- [ ] Include commands run and exit statuses when command results exist.
- [ ] Include skipped checks and reasons.
- [ ] Include auditor failures and incomplete checks.
- [ ] Implement report writer:
      - create reports directory
      - write date report
      - avoid overwriting by using timestamp fallback
      - update `reports/latest.md`
- [ ] Implement fresh failure report writer for fatal workflow errors.
- [ ] Ensure all report content is redacted before writing.

Tests:

- [ ] Redacts webhook URL.
- [ ] Redacts token/password/api-key lines.
- [ ] Redacts authorization headers.
- [ ] Redacts private key block marker content.
- [ ] Markdown renderer includes all required sections.
- [ ] Empty sections use `None found.`.
- [ ] Report writer updates latest report.
- [ ] Report writer avoids overwriting existing report.
- [ ] Failure report is fresh and does not reuse stale `latest.md`.
- [ ] Golden sample report test uses synthetic data only.

Validation:

- [ ] Generated local report for synthetic input is readable and public-safe.
- [ ] `reports/` generated files remain ignored by git.

Exit criteria:

- [ ] A deterministic non-graph pipeline can produce a complete local Markdown
      report from synthetic repo results.

### Phase 6: LangGraph Sequential Workflow

Goal: wire the deterministic components into a LangGraph workflow that can run
end to end without LLM, Discord, safe commands, systemd, or parallel fan-out.

Deliverables:

- [ ] Implement graph builder in `graph.py`.
- [ ] Implement `load_config` node.
- [ ] Implement `prepare_run` node.
- [ ] Implement `select_repos` node.
- [ ] Implement sequential per-repo inspection node or loop.
- [ ] Implement `merge_results` node.
- [ ] Implement deterministic summary generation for `--no-llm`.
- [ ] Implement `redact_report` node.
- [ ] Implement `render_markdown` node.
- [ ] Implement `write_report` node.
- [ ] Implement `handle_failure` path.
- [ ] Ensure graph state is serializable for tests.
- [ ] Ensure one repository failure becomes a finding/incomplete result when
      possible instead of crashing the whole run.
- [ ] Implement CLI:
      `langgraph-maintenance run --config examples/repos.yaml --no-llm`.
- [ ] Add `--output-dir` option.
- [ ] Add `--dry-run` option that performs checks and renders output without
      writing report files.

Tests:

- [ ] Workflow smoke test with one synthetic repo.
- [ ] Workflow smoke test with two synthetic repos.
- [ ] Workflow continues when one repo path is missing.
- [ ] Workflow writes latest report.
- [ ] Workflow dry run does not write files.
- [ ] Workflow no-LLM mode requires no API key.
- [ ] Fatal config failure writes/returns a useful failure result.

Validation:

- [ ] `langgraph-maintenance run --config examples/repos.yaml --no-llm --dry-run`
      works.
- [ ] `langgraph-maintenance run --config <temp-config> --no-llm` writes a
      report.
- [ ] `python -m pytest` passes.

Exit criteria:

- [ ] This is the core MVP. The project is now a real LangGraph app.

### Phase 7: Safe Command Execution

Goal: add explicitly configured command execution while preserving the
report-only safety model.

Deliverables:

- [ ] Implement command runner wrapper.
- [ ] Enforce per-command timeout.
- [ ] Enforce per-repo working directory.
- [ ] Capture exit code.
- [ ] Capture bounded stdout/stderr excerpts.
- [ ] Redact command output before storing it.
- [ ] Mark timeout as incomplete/skipped check with evidence.
- [ ] Support shell command strings only from validated `safe_commands`.
- [ ] Prefer argv/non-shell execution for internal built-in commands.
- [ ] Add built-in mapping from configured checks to command labels:
      - `tests`
      - `lint`
      - `build`
      - `python-syntax`
- [ ] If a configured check has no safe command, mark it skipped with reason.
- [ ] Ensure command execution never runs fix/format/upgrade/cleanup commands.
- [ ] Add optional writable temp/cache environment support outside the target
      repository for tools that need caches.

Tests:

- [ ] Safe command exits `0`.
- [ ] Safe command exits nonzero and becomes a finding.
- [ ] Safe command timeout is reported.
- [ ] Unsafe command is rejected during config validation.
- [ ] Command stdout/stderr is bounded and redacted.
- [ ] Missing safe command is skipped.
- [ ] Working directory is the target repo.
- [ ] Command runner does not mutate synthetic repo except explicitly expected
      tool cache behavior in temp dirs.

Validation:

- [ ] Synthetic config can run a harmless command such as
      `python -c "print('ok')"`.
- [ ] Unsafe command fixtures fail before execution.

Exit criteria:

- [ ] Configured tests/lint/build checks are supported without weakening the
      safety boundary.

### Phase 8: Optional LLM Summarization

Goal: add selective model use for summarization and next actions while keeping
the default demo runnable without credentials.

Deliverables:

- [ ] Decide provider integration. Recommended default: OpenAI-compatible
      provider through environment variables, with no hard-coded model secrets.
- [ ] Add provider-specific dependency only if needed.
- [ ] Implement prompt template for summary generation.
- [ ] Input to LLM must be structured findings, not raw unredacted logs.
- [ ] Redact before LLM call unless explicitly documented otherwise.
- [ ] Require structured output for:
      - executive summary
      - suggested next actions
      - optional finding grouping notes
- [ ] Implement no-LLM fallback that remains the default for tests and sample
      demos.
- [ ] Add CLI flags:
      - `--no-llm`
      - `--llm`
      - optional `--model`
- [ ] Ensure missing API key produces a clear skip/fallback message rather than
      a crash when no-LLM mode is active.

Tests:

- [ ] No-LLM mode does not import or call provider clients.
- [ ] Missing API key in LLM mode fails clearly or falls back according to
      documented behavior.
- [ ] Prompt input is redacted.
- [ ] Mocked LLM structured output is parsed correctly.
- [ ] Malformed LLM output falls back to deterministic summary or produces an
      incomplete-check warning.

Validation:

- [ ] Public demo works without API key.
- [ ] Optional local LLM run can enrich report summaries.

Exit criteria:

- [ ] The project demonstrates selective, controlled LLM usage rather than
      replacing deterministic checks with model calls.

### Phase 9: Discord Delivery

Goal: deliver a safe summary of the generated report to Discord without exposing
secrets or requiring Discord for the default demo.

Deliverables:

- [ ] Implement Discord sender using standard library or a minimal dependency.
- [ ] Load webhook only from environment:
      - `LANGGRAPH_MAINTENANCE_DISCORD_WEBHOOK_URL`
      - fallback `DISCORD_WEBHOOK_URL`
- [ ] Support `.env` locally without committing it.
- [ ] Never print webhook value.
- [ ] Extract summary sections from full report.
- [ ] Support `--summary-only`.
- [ ] Support safe chunking below Discord message limits.
- [ ] Redact content immediately before sending.
- [ ] Handle HTTP errors with clear messages.
- [ ] Add CLI command:
      `langgraph-maintenance send reports/latest.md --summary-only`.
- [ ] Add optional workflow flag to send after successful run.
- [ ] Ensure failed runs send fresh failure report, not stale latest report.

Tests:

- [ ] Summary extraction test.
- [ ] Chunking test.
- [ ] Missing webhook error test.
- [ ] Webhook redaction test.
- [ ] Mock HTTP success test.
- [ ] Mock HTTP failure test.
- [ ] Fresh failure report send path test.

Validation:

- [ ] Local webhook test succeeds when `.env` is configured.
- [ ] Public tests do not require a webhook.

Exit criteria:

- [ ] Discord delivery is production-usable but optional.

### Phase 10: Parallel Fan-Out/Fan-In

Goal: upgrade the graph from sequential repo inspection to portfolio-worthy
parallel repository branches while preserving deterministic behavior.

Deliverables:

- [ ] Implement LangGraph fan-out over enabled repositories.
- [ ] Keep per-repo state isolated.
- [ ] Merge per-repo results deterministically.
- [ ] Preserve stable report ordering by config order or repo name.
- [ ] Continue when one repo fails unless marked `required`.
- [ ] Add configurable max concurrency if supported/needed.
- [ ] Add clear logs for repo start/end/failure.
- [ ] Ensure command timeouts still apply per repo.

Tests:

- [ ] Parallel workflow returns same normalized findings as sequential workflow
      for synthetic repos.
- [ ] One repo failure does not prevent other repo reports.
- [ ] Required repo failure follows documented behavior.
- [ ] Report ordering is stable.

Validation:

- [ ] Run against multiple synthetic repos.
- [ ] Run against at least one real local test repo only if public-safe and not
      committed into examples.

Exit criteria:

- [ ] LangGraph orchestration is visible and meaningful for portfolio review.

### Phase 11: Scheduling And Runtime Wrappers

Goal: make the agent usable as a scheduled local maintenance job.

Deliverables:

- [ ] Add `scripts/run_maintenance_check.sh`.
- [ ] Add `scripts/run_and_send.sh`.
- [ ] Scripts load local `.env` if present.
- [ ] Scripts enforce whole-run timeout through
      `LANGGRAPH_MAINTENANCE_TIMEOUT_SECONDS`.
- [ ] Scripts write a fresh failure report when the run fails.
- [ ] Scripts never send stale `reports/latest.md` after failure.
- [ ] Add `systemd/langgraph-maintenance-agent.service`.
- [ ] Add `systemd/langgraph-maintenance-agent.timer`.
- [ ] Timer runs daily at 11:00 AM local system time.
- [ ] Document user-level systemd install commands.
- [ ] Document manual fallback commands.

Tests:

- [ ] `bash -n` passes for shell scripts.
- [ ] Failure report path can be simulated without invoking real Discord.
- [ ] systemd units have expected `OnCalendar=*-*-* 11:00:00`.

Validation:

- [ ] Manual script run succeeds with sample config.
- [ ] Optional local systemd validation succeeds if environment permits.

Exit criteria:

- [ ] The project can run manually and has documented scheduled deployment.

### Phase 12: Documentation, Portfolio Polish, And Public Release Prep

Goal: make the repository understandable, credible, and safe for public
publication.

Deliverables:

- [ ] Expand `README.md` with:
      - short pitch
      - feature list
      - safety model
      - quick start
      - no-LLM demo
      - optional LLM mode
      - optional Discord mode
      - test commands
- [ ] Expand `ARCHITECTURE.md` with:
      - graph diagram
      - node descriptions
      - state schema overview
      - deterministic vs LLM boundary
      - safety boundary
      - failure handling
- [ ] Add `docs/portfolio-notes.md` explaining what the project demonstrates.
- [ ] Add `docs/safety.md` if not already complete.
- [ ] Add synthetic screenshots or terminal output examples.
- [ ] Add `examples/sample-report.md`.
- [ ] Add GitHub Actions CI if publishing to GitHub:
      - install
      - lint
      - tests
      - optional type check
- [ ] Add final public-safety scan instructions.
- [ ] Decide license and add `LICENSE`.
- [ ] Add release checklist.

Public-safety release checklist:

- [ ] No `.env` files tracked.
- [ ] No generated private reports tracked.
- [ ] No raw event logs tracked.
- [ ] No real Discord webhook URLs.
- [ ] No API keys.
- [ ] No private repository names or internal URLs in examples.
- [ ] No raw output copied from private repositories.
- [ ] `git status --short --ignored` reviewed before publication.
- [ ] Secret scan command documented and run.

Validation:

- [ ] Fresh clone can run no-LLM demo.
- [ ] Fresh clone can run tests.
- [ ] README explains optional credentials without requiring them.

Exit criteria:

- [ ] Repository is ready to publish as a portfolio project.

## Open Questions

- Which LLM provider should be the default for the portfolio version?
- Should the default demo run in no-LLM mode for easier reviewer setup?
- Should generated reports be local-only, or should synthetic sample reports be
  committed under `examples/`?
- Should the first release support only Python repos, or generic repo metadata
  plus configured commands?
- Should Discord delivery be optional in the MVP or required for completion?

## Success Criteria

- A reviewer can clone the public repo, run tests, and understand the design
  without private credentials.
- A developer can configure local repositories and run a report-only audit.
- The workflow never modifies target repositories.
- Failure cases are visible and do not produce stale success reports.
- The codebase demonstrates LangGraph clearly enough to be credible portfolio
  evidence.
