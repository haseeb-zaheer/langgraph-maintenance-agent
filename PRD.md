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

The MVP is complete when:

- A CLI can run the LangGraph workflow against a public-safe sample config.
- The workflow scans only enabled configured repositories.
- The workflow performs read-only metadata/docs/static checks.
- The workflow can optionally run explicitly configured safe commands.
- Findings are normalized into typed records with severity.
- The final local Markdown report is generated.
- Discord delivery works through an environment variable webhook.
- Secret redaction is applied before report delivery.
- Unit tests and at least one workflow smoke test pass.
- Documentation explains setup, safety, architecture, and portfolio value.

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
- [ ] Choose package name: `langgraph_maintenance_agent`.
- [ ] Create `src/langgraph_maintenance_agent/`.
- [ ] Create `tests/`.
- [ ] Create `config/`.
- [ ] Create `examples/`.
- [ ] Create `reports/` with only `.gitkeep` committed.
- [ ] Create `scripts/`.
- [ ] Create `systemd/`.
- [ ] Add `.gitignore` for `.env`, caches, generated reports, logs, and virtual
      environments.
- [ ] Add `.env.example` with placeholders only.
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

## Proposed Implementation Phases

### Phase 1: Public-Safe Scaffold

- [ ] Create Python package skeleton.
- [ ] Add config schema.
- [ ] Add `.gitignore` and `.env.example`.
- [ ] Add README and architecture docs.
- [ ] Add synthetic example config.
- [ ] Add initial tests for config loading.

### Phase 2: Deterministic Repo Inspection

- [ ] Implement git metadata checks.
- [ ] Implement docs checks.
- [ ] Implement static marker scanning.
- [ ] Implement dependency manifest detection.
- [ ] Implement command runner with timeouts.
- [ ] Add tests using temporary git repositories.

### Phase 3: LangGraph Workflow

- [ ] Define graph state.
- [ ] Implement workflow nodes.
- [ ] Add fan-out/merge behavior.
- [ ] Add failure routing.
- [ ] Add no-LLM mode.
- [ ] Add workflow smoke tests.

### Phase 4: Reporting And Redaction

- [ ] Implement finding schema.
- [ ] Implement severity grouping.
- [ ] Implement Markdown renderer.
- [ ] Implement secret redaction.
- [ ] Implement report persistence.
- [ ] Add golden sample report tests.

### Phase 5: Discord And Scheduling

- [ ] Implement Discord sender.
- [ ] Add chunking and summary-only mode.
- [ ] Add wrapper scripts.
- [ ] Add systemd units.
- [ ] Validate manual full flow.
- [ ] Document systemd setup.

### Phase 6: Portfolio Polish

- [ ] Add architecture diagram.
- [ ] Add sample report.
- [ ] Add screenshots or terminal output examples.
- [ ] Add CI workflow if publishing to GitHub.
- [ ] Add final public-safety scan before publication.

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
