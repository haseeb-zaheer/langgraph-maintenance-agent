# LangGraph Routine Maintenance Agent PRD

## Summary

Build a public portfolio-quality LangGraph application that performs scheduled,
report-only maintenance reviews over an explicit allowlist of local
repositories.

The agent should inspect repository health, dependency metadata, configured
lint/test/build commands, documentation drift, dirty worktrees, and suspicious
maintenance risks. It should be genuinely agentic: OpenRouter-backed LLM agents
should reason over each configured repository by calling constrained,
public-safe tools. It must never modify target repositories. It should write a
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
- An OpenRouter-backed repository inspector agent can inspect repositories using
  constrained tools.
- The workflow performs read-only metadata/docs/static checks through safe tools.
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

The project should be workflow-first and agentic. LangGraph coordinates explicit
state transitions, OpenRouter-backed LLM agents decide which safe repository
tools to call, and deterministic Python enforces configuration, tool safety,
redaction, report rendering, and persistence.

```text
systemd timer / manual CLI
  -> Python CLI
    -> LangGraph supervisor workflow
      -> load + validate config
      -> prepare run context
      -> select enabled repos
      -> fan out repo inspector agents
        -> repo inspector agent
          -> safe tools:
            -> git_status
            -> latest_commit
            -> list_files
            -> read_safe_file
            -> search_static_markers
            -> detect_dependency_manifests
            -> run_configured_safe_command
          -> structured repo findings
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

  agents/
    supervisor.py
    repo_inspector.py
    prompts.py

  tools/
    git.py
    files.py
    search.py
    dependencies.py
    commands.py
    registry.py

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
    openrouter.py
    types.py
    structured_outputs.py

  runtime/
    paths.py
    logging.py
    errors.py
```

### Agentic Tool-Use Model

The repo inspector should be an LLM agent, not just a deterministic function.
For each configured repository, it should receive:

- repo name
- configured path
- enabled checks
- allowed command labels
- timeout guidance
- safety instructions

It should call only registered tools. The LLM must never receive unrestricted
shell access or direct arbitrary file access.

Required tools:

- `git_status(repo_name)`: return branch, dirty state, ahead/behind summary, and
  concise status metadata.
- `latest_commit(repo_name)`: return latest commit hash/date/subject when
  available.
- `list_files(repo_name, patterns=None)`: list public-safe file paths while
  excluding sensitive paths.
- `read_safe_file(repo_name, relative_path)`: read only approved documentation
  and manifest files; reject `.env`, logs, private keys, databases, raw reports,
  and other sensitive paths.
- `search_static_markers(repo_name)`: search TODO/FIXME/HACK and return bounded
  public-safe path/line summaries.
- `detect_dependency_manifests(repo_name)`: identify Python, Node, Docker, dbt,
  and other dependency manifests without running package managers.
- `run_configured_safe_command(repo_name, command_label)`: run only commands
  configured and validated in `safe_commands`.

Tool output must be bounded and redacted before it is added to graph state or
sent back into the model.

### Deterministic Logic Vs LLM Agent Logic

Use deterministic Python for:

- Config loading and validation.
- Repository allowlist enforcement.
- Tool registry and repo-name-to-path resolution.
- Tool safety checks.
- Sensitive path blocking.
- Safe command execution mechanics.
- Timeout handling.
- Secret redaction.
- Markdown rendering.
- Discord delivery.
- Failure report generation.

Use OpenRouter-backed LLM agents for:

- Deciding which safe tools to call for a configured repo.
- Interpreting safe tool outputs.
- Producing structured repository findings.
- Writing executive summaries and suggested next actions.
- Explaining ambiguous risks from already redacted evidence.

The portfolio value should come from constrained tool-using agents, not from
unrestricted shell access. The deterministic layer must remain the safety
boundary.

### LangGraph Node Design

The primary graph should include these nodes:

- `load_config`: read and validate the allowlist config.
- `prepare_run`: create run id, timestamps, report paths, and output dirs.
- `select_repos`: filter enabled repositories.
- `build_tool_registry`: create configured, repo-scoped safe tools.
- `inspect_repo_agent`: run the repo inspector agent for one configured repo.
- `normalize_agent_output`: validate structured agent output into typed
  findings and skipped checks.
- `merge_results`: deduplicate and group findings across repositories.
- `summarize_with_agent`: create executive summary and next actions from
  structured findings.
- `redact_report`: remove secrets and unsafe values before persistence/delivery.
- `render_markdown`: produce the full local Markdown report.
- `write_report`: write timestamped report and update `reports/latest.md`.
- `send_discord_summary`: send a safe summary or chunks to Discord.
- `handle_failure`: write and send a fresh failure report on workflow failure.

### Execution Model

The first agentic workflow may inspect repositories sequentially for simplicity.
The portfolio-ready version should add LangGraph fan-out/fan-in:

```text
select_repos
  -> inspect_repo_agent(repo A)
  -> inspect_repo_agent(repo B)
  -> inspect_repo_agent(repo N)
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

Agent-specific state should also track:

- tool call history
- bounded tool outputs
- model name/provider
- structured agent output
- redaction warnings
- incomplete agent runs

### Safety Boundary

The safety boundary must be enforced in code, not only prompts:

- Config allowlist only.
- Safe command allowlist only.
- Command timeouts.
- Blocked unsafe command keywords.
- LLM agents can only call registered tools.
- Tools resolve repo names through validated config; agents do not pass raw
  filesystem roots.
- `read_safe_file` blocks sensitive paths and extensions.
- No `.env` reads from target repositories.
- No raw private log reads.
- Redaction before report persistence and delivery.
- Generated reports ignored by git.
- Synthetic public-safe examples only.
- Fresh failure reports instead of stale `latest.md` reuse.

## Architecture Checklist

### Repository Scaffold

- [x] Initialize Python project metadata with `pyproject.toml`.
- [x] Choose import package name: `langgraph_maintenance_agent`.
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
- [x] Add `README.md`.
- [x] Add `ARCHITECTURE.md`.
- [x] Add license decision before publishing.

### Core Dependencies

- [x] Add LangGraph.
- [ ] Add OpenRouter-compatible model client support for agent calls.
- [ ] Add LangChain/OpenAI integration only if it is the chosen adapter for
      OpenRouter-compatible tool calling.
- [x] Add Pydantic for config and report schemas.
- [x] Add PyYAML or equivalent for config loading.
- [x] Add pytest.
- [x] Add ruff or another linter.
- [x] Add mypy or pyright if type checking is included.
- [ ] Keep dependency list minimal and explain each major dependency.

### Configuration Model

- [x] Define config schema for repositories.
- [x] Support fields: `name`, `path`, `enabled`, `checks`,
      `safe_commands`, `timeout_seconds`, `notes`.
- [ ] Support optional agent/model settings through environment variables and
      non-secret config:
      - provider name, default `openrouter`
      - model name env override
      - max tool calls per repo
      - max agent iterations per repo
      - no-LLM or deterministic fallback mode
- [x] Support optional report settings.
- [x] Support model secrets only through environment variables, never config
      files.
- [x] Support Discord delivery enable/disable through config and CLI flags,
      defaulting to disabled.
- [ ] Validate that repo paths are absolute or intentionally relative to a safe
      base directory.
- [x] Reject duplicate repo names.
- [x] Reject enabled repos without a path.
- [x] Reject unknown check names unless explicitly allowed as custom checks.
- [x] Reject unsafe command names such as `fix`, `format`, `upgrade`, `delete`,
      `reset`, `checkout`, `commit`, or `clean`.
- [x] Provide `examples/repos.yaml` with synthetic public-safe paths.
- [x] Never include real private webhook URLs or tokens in config.

### LangGraph State Design

- [x] Define a typed graph state.
- [x] Include run metadata: run id, start time, config path, output paths.
- [x] Include repository configs.
- [x] Include per-repo check results.
- [x] Include findings.
- [x] Include skipped checks.
- [x] Include command execution summaries.
- [x] Include redaction warnings.
- [x] Include final report content.
- [x] Include delivery status.
- [x] Include fatal errors and partial failures.
- [ ] Include agent/tool-call history with bounded redacted outputs.
- [ ] Include model provider and model name used for each agent run.
- [x] Include incomplete agent runs and tool failures.
- [x] Ensure state is serializable for debugging and tests.

### Workflow Nodes

- [x] `load_config`: read and validate allowlist config.
- [x] `prepare_run`: create run id, output paths, and runtime context.
- [x] `select_repos`: filter enabled repositories.
- [x] `build_tool_registry`: create repo-scoped safe tools for enabled repos.
- [x] `inspect_repo_agent`: run an LLM repo inspector agent with safe tools.
- [x] `normalize_agent_output`: validate structured agent output into findings,
      skipped checks, command summaries, and errors.
- [x] `merge_results`: dedupe and group findings.
- [x] `summarize_with_agent`: produce executive summary and suggested next
      actions from structured findings.
- [x] `redact_report`: remove secret patterns and unsafe values.
- [x] `render_markdown`: create the local full report.
- [x] `write_report`: persist report and latest pointer/copy.
- [x] `send_discord_summary`: send safe summary or full chunks based on settings.
- [x] `handle_failure`: write a fresh failure report if the workflow fails.

### Graph Routing

- [ ] Fan out enabled repositories for parallel agent inspection when supported.
- [ ] Continue if one repository fails, unless config marks it required.
- [ ] Route command timeouts to skipped/incomplete check records.
- [ ] Route agent iteration/tool-call limits to incomplete check records.
- [ ] Route malformed structured agent output to validation errors and
      deterministic fallback where possible.
- [x] Route redaction hits to a warning section without exposing values.
- [x] Route fatal configuration errors to a local failure report.
- [x] Ensure failed runs never send stale previous reports.

### Agent Tools And Command Execution

- [ ] Implement a repo-scoped tool registry.
- [ ] Implement `git_status(repo_name)`.
- [ ] Implement `latest_commit(repo_name)`.
- [ ] Implement `list_files(repo_name, patterns=None)`.
- [ ] Implement `read_safe_file(repo_name, relative_path)`.
- [ ] Implement `search_static_markers(repo_name)`.
- [ ] Implement `detect_dependency_manifests(repo_name)`.
- [ ] Implement `run_configured_safe_command(repo_name, command_label)`.
- [ ] Ensure tools accept repo names, not arbitrary filesystem roots.
- [ ] Ensure `read_safe_file` rejects `.env`, logs, databases, private keys, raw
      reports, binary files, and paths outside the repo.
- [ ] Ensure tool outputs are bounded and redacted before model/state use.
- [ ] Implement a command runner wrapper for configured safe commands.
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
- [ ] Add tests for sensitive path rejection.
- [ ] Add tests proving agents cannot call unregistered tools.
- [ ] Add tests for unsafe command rejection.

### Repository Tool Capabilities

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

### Agent And LLM Usage

- [x] Use OpenRouter as the preferred provider.
- [x] Load `OPENROUTER_API_KEY` from environment only.
- [x] Load model name from `LANGGRAPH_MAINTENANCE_LLM_MODEL`, with a documented
      safe default placeholder.
- [x] Use LLM agents for repo inspection and report summarization.
- [x] Use deterministic Python for config parsing, tool safety, command
      execution mechanics, redaction, and report writing.
- [x] Require structured output from repo inspector agents.
- [x] Require structured output from summary agent.
- [x] Add prompt templates under `src/.../prompts/` or `prompts/`.
- [ ] Keep prompts public-safe and free of private examples.
- [ ] Add tests or golden fixtures for prompt inputs/outputs where practical.
- [x] Support a no-LLM deterministic fallback mode for tests and public demos.
- [x] Add mocked model tests for tool-call and structured-output flows.

### Report Format

- [x] Generate `reports/YYYY-MM-DD-routine-maintenance.md`.
- [x] Generate a timestamped filename if the date report already exists.
- [x] Update `reports/latest.md`.
- [x] Include executive summary.
- [x] Include critical findings.
- [x] Include high priority findings.
- [x] Include medium priority findings.
- [x] Include low priority findings.
- [x] Include repositories scanned.
- [x] Include repositories skipped.
- [x] Include dependency concerns.
- [x] Include test/lint/build results.
- [x] Include dirty worktrees.
- [x] Include suggested next actions.
- [x] Include appendix with per-repo details.
- [x] Include commands run and exit statuses.
- [x] Include skipped checks and reasons.
- [x] Include auditor failures or incomplete checks.
- [x] Use `None found.` for empty severity sections.

### Discord Delivery

- [x] Load webhook from environment only.
- [ ] Support `.env` locally without committing it.
- [x] Prefer a routine-specific env var such as
      `LANGGRAPH_MAINTENANCE_DISCORD_WEBHOOK_URL`.
- [x] Support optional fallback `DISCORD_WEBHOOK_URL`.
- [x] Redact report before sending.
- [x] Extract a short summary for Discord.
- [x] Split long messages into multiple Discord messages with each `content`
      payload below Discord's 2,000-character message limit.
- [x] Handle HTTP failures clearly.
- [x] Never print the webhook URL.
- [x] Add `--summary-only` option.
- [x] Add tests for chunking and redaction.

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
- [x] Support `--summary-only`.
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
- [x] Python package metadata exists.
- [x] Initial application code exists.
- [x] Initial smoke tests exist.
- [x] README, architecture doc, examples, and sample report exist.

### Phase 1: Project Foundation And Public-Safe Scaffold

Goal: turn the documentation scaffold into a runnable Python project skeleton
without implementing the full agent yet.

Deliverables:

- [x] Add `pyproject.toml`.
- [x] Use package name `langgraph-maintenance-agent` for distribution metadata.
- [x] Use import package `langgraph_maintenance_agent`.
- [x] Set Python requirement to a modern stable version, preferably
      `>=3.11,<3.15` unless tooling requires otherwise.
- [x] Add runtime dependencies:
      - `langgraph`
      - `pydantic`
      - `PyYAML` or another YAML parser
- [x] Add optional LLM dependencies only if the implementation needs them in the
      same phase. Prefer delaying provider-specific packages until Phase 5.
- [x] Add dev dependencies:
      - `pytest`
      - `ruff`
      - type checker if chosen, such as `mypy` or `pyright`
- [x] Configure console script:
      `langgraph-maintenance = langgraph_maintenance_agent.cli:main`.
- [x] Add package `__init__.py`.
- [x] Add initial module files:
      - `cli.py`
      - `config.py`
      - `schemas.py`
      - `state.py`
      - `graph.py`
- [x] Add subpackages with `__init__.py`:
      - `checks/`
      - `reporting/`
      - `runtime/`
      - `llm/`
- [x] Add `README.md` with a concise public-safe project summary and current
      development status.
- [x] Add `ARCHITECTURE.md` with the target architecture from this PRD.
- [x] Add `docs/safety.md` describing public-repo safety, allowlist-only scans,
      secret redaction, and report-only behavior.
- [x] Add `examples/repos.yaml` using synthetic paths only.
- [x] Add `examples/sample-report.md` with synthetic findings only.
- [x] Add a license file or explicitly document that license selection is
      pending before publication.

Implementation notes:

- Keep the first scaffold simple. Do not add Discord, systemd, safe command
  execution, or LLM calls in this phase.
- Do not include real local repository paths in public examples.
- Do not commit generated reports except synthetic examples under `examples/`.

Validation:

- [x] `python -m pytest` runs, even if only smoke tests exist.
- [x] `ruff check .` runs if ruff is configured.
- [x] `langgraph-maintenance --help` works after editable install.
- [x] `git status --short --ignored` shows no accidental secret/runtime files
      staged.

Exit criteria:

- [x] A future session can install the project locally and run the empty CLI.
- [x] Public-facing docs explain what the project is and what is not implemented
      yet.

### Phase 2: Config Schema And Validation

Goal: implement the configuration boundary before any repository scanning exists.
This is the main safety gate for the entire project.

Deliverables:

- [x] Implement `RepoConfig` schema.
- [x] Implement `CheckName` or equivalent constrained check representation.
- [x] Implement `SafeCommand` schema.
- [x] Implement top-level `AppConfig` schema.
- [x] Support repo fields:
      - `name`
      - `path`
      - `enabled`
      - `checks`
      - `safe_commands`
      - `timeout_seconds`
      - `notes`
      - optional `required`
- [x] Support report settings:
      - output directory
      - report filename prefix
      - whether to update `latest.md`
      - whether Discord delivery is enabled
- [x] Support runtime settings through environment variables, not committed
      config secrets.
- [x] Implement `load_config(path: Path) -> AppConfig`.
- [x] Validate duplicate repo names are rejected.
- [x] Validate enabled repos require a path.
- [x] Validate unknown check names are rejected unless custom checks are
      explicitly supported later.
- [x] Validate unsafe command labels are rejected, including names containing:
      `fix`, `format`, `upgrade`, `delete`, `remove`, `reset`, `checkout`,
      `commit`, `clean`, `migrate`, `install`.
- [x] Validate unsafe command strings are rejected when they clearly contain
      destructive operations such as:
      `rm -rf`, `git reset`, `git checkout`, `git clean`, `npm audit fix`,
      `pip install -U`, `uv add`, `poetry add`, `alembic upgrade`.
- [x] Decide and document whether shell command strings are allowed. Recommended:
      allow shell strings only for explicitly configured `safe_commands`, but
      run all built-in checks without shell where possible.
- [x] Implement CLI command:
      `langgraph-maintenance validate-config examples/repos.yaml`.
- [x] Add `examples/repos.yaml` that validates without requiring private paths.

Tests:

- [x] Valid config loads successfully.
- [x] Missing file produces a useful error.
- [x] Duplicate repo names fail.
- [x] Enabled repo without path fails.
- [x] Unknown check fails.
- [x] Unsafe safe-command label fails.
- [x] Unsafe safe-command string fails.
- [x] Disabled repo with incomplete details is handled according to documented
      behavior.
- [x] Example config stays public-safe.

Validation:

- [x] `langgraph-maintenance validate-config examples/repos.yaml` exits `0`.
- [x] Invalid config fixtures exit nonzero or raise expected validation errors.

Exit criteria:

- [x] No repository scanning can occur without passing config validation.

### Phase 3: Deterministic Schemas, Findings, And Runtime Utilities

Goal: define the typed data model used by checks, graph state, reporting, and
tests before wiring the graph.

Deliverables:

- [x] Implement severity enum:
      - `critical`
      - `high`
      - `medium`
      - `low`
      - optional `info`
- [x] Implement finding category enum:
      - `security`
      - `dependency`
      - `test`
      - `build`
      - `git`
      - `docs`
      - `static`
      - `runtime`
      - `configuration`
- [x] Implement `Finding` schema with:
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
- [x] Implement `CommandResult` schema with:
      - command label
      - command string or argv
      - working directory
      - exit code
      - timed out flag
      - bounded stdout excerpt
      - bounded stderr excerpt
      - started/ended timestamps or duration
- [x] Implement `SkippedCheck` schema.
- [x] Implement `RepoResult` schema.
- [x] Implement `DeliveryStatus` schema.
- [x] Implement `AgentError` schema.
- [x] Implement `AgentState` using `TypedDict` or Pydantic-compatible state.
- [x] Implement deterministic finding fingerprinting for dedupe.
- [x] Implement runtime path helpers for report names:
      `YYYY-MM-DD-routine-maintenance.md` and timestamp fallback.
- [x] Implement bounded text helpers for command output excerpts.

Tests:

- [x] Finding serialization round trip.
- [x] Fingerprints are stable for equivalent findings.
- [x] Fingerprints differ for meaningfully different findings.
- [x] Command output excerpts are bounded.
- [x] Report path helper avoids overwriting existing date report.
- [x] Agent state can be serialized to JSON-safe structures.

Validation:

- [x] Unit tests pass.
- [x] Type checker passes if configured.

Exit criteria:

- [x] Later phases can return structured results without inventing ad hoc
      dictionaries.

### Phase 4: Safe Repository Tool Layer

Goal: implement the constrained Python tools that LLM agents are allowed to use.
This phase creates the agent's tool surface but does not call an LLM yet.

Deliverables:

- [x] Create `tools/` package with repo-scoped tool modules and registry.
- [x] Implement `ToolContext` containing validated config, repo map, timeouts,
      output limits, and redaction hooks.
- [x] Implement tool result schemas for success, skipped, and error outcomes.
- [x] Implement `git_status(repo_name)`:
      - path existence
      - git repo detection
      - branch
      - latest status summary
      - dirty/untracked summary
      - ahead/behind when available
- [x] Implement `latest_commit(repo_name)`:
      - hash
      - date
      - subject
      - graceful non-git handling
- [x] Implement `list_files(repo_name, patterns=None)`:
      - public-safe relative paths only
      - configurable max file count
      - excludes sensitive paths and ignored runtime directories
- [x] Implement `read_safe_file(repo_name, relative_path)`:
      - allow only safe docs/manifests/source snippets needed for inspection
      - reject path traversal
      - reject `.env`, logs, databases, private keys, raw reports, binary files,
        and oversized files
      - return bounded, redacted content
- [x] Implement `search_static_markers(repo_name)`:
      - TODO/FIXME/HACK search
      - bounded path/line summaries
      - no sensitive file reads
- [x] Implement `detect_dependency_manifests(repo_name)`:
      - Python: `pyproject.toml`, `requirements*.txt`, `uv.lock`,
        `poetry.lock`
      - Node: `package.json`, lockfiles
      - Docker: `Dockerfile`, `compose.yaml`, `docker-compose.yml`
      - dbt: `dbt_project.yml`
- [x] Initially implemented `run_configured_safe_command(repo_name,
      command_label)` as a skipped stub; Phase 7 replaces it with bounded
      configured command execution.
- [x] Ensure every tool accepts a repo name and never arbitrary raw root paths.
- [x] Ensure every tool output is bounded and redacted before state/model use.
- [x] Convert tool outputs into structures reusable by agent prompts and
      deterministic fallback tests.

Tests:

- [x] Temporary non-git directory is reported correctly.
- [x] Temporary git repo with clean state is reported correctly.
- [x] Temporary git repo with dirty state is reported correctly.
- [x] `list_files` excludes sensitive paths.
- [x] `read_safe_file` reads safe docs/manifests.
- [x] `read_safe_file` rejects `.env`, logs, private keys, path traversal, and
      oversized files.
- [x] Dependency manifest detection works for synthetic files.
- [x] Static marker scan finds TODO/FIXME/HACK without reading ignored secrets.
- [x] Tool outputs are bounded and redacted.
- [x] Unknown repo names are rejected.
- [x] Command tool returned skipped before Phase 7.

Validation:

- [x] Tests create only temporary synthetic repositories.
- [x] No test fixture contains private paths or secrets.

Exit criteria:

- [x] The project exposes a safe, tested tool layer that an LLM agent can call.

### Phase 5: OpenRouter Model Client And Agent Contracts

Goal: add OpenRouter-backed agent infrastructure, prompts, and structured output
contracts without yet wiring the full LangGraph workflow.

Deliverables:

- [x] Add OpenRouter client module under `llm/openrouter.py`.
- [x] Use environment variable `OPENROUTER_API_KEY`; never read it from config.
- [x] Use `LANGGRAPH_MAINTENANCE_LLM_MODEL` for the default model override.
- [x] Default OpenRouter model is `deepseek/deepseek-v4-flash`.
- [x] Document an example model placeholder, not a real private preference.
- [ ] Add provider/model fields to runtime state and run metadata.
- [x] Define structured output schema for repo inspector agent:
      - repo identity
      - checks attempted
      - tool calls used
      - findings
      - skipped checks
      - command notes
      - dependency notes
      - incomplete checks
      - confidence/needs human review flags
- [x] Define structured output schema for summary agent:
      - executive summary
      - critical/high/medium/low highlights
      - suggested next actions
      - auditor limitations
- [x] Add repo inspector prompt:
      - must use only supplied tools
      - must not request arbitrary shell/file access
      - must not ask tools for secrets
      - must return structured output
- [ ] Add summary prompt:
      - takes redacted structured findings only
      - does not invent commands or findings
- [x] Add no-LLM deterministic fallback contracts for tests and demos.
- [x] Use mocks/fakes for all model tests; public tests must not require
      OpenRouter credentials.

Tests:

- [x] Missing `OPENROUTER_API_KEY` in LLM mode fails clearly.
- [x] No-LLM mode does not require or read `OPENROUTER_API_KEY`.
- [x] Model name is loaded from env override when set.
- [x] Repo inspector structured output validates.
- [x] Summary structured output validates.
- [x] Malformed model output becomes an incomplete agent result.
- [ ] Prompts do not contain private examples or raw local paths.

Validation:

- [x] Unit tests use mocked model responses only.
- [x] Public demo still works without API keys.

Exit criteria:

- [x] The project can instantiate OpenRouter-backed agent contracts safely, and
      tests can validate agent behavior without real network/model calls.

### Phase 6: LangGraph Sequential Tool-Using Agent Workflow

Goal: wire config, tool registry, repo inspector agent, structured output
normalization, redaction, and report writing into the first end-to-end LangGraph
workflow. This phase creates the core agentic MVP.

Deliverables:

- [x] Implement graph builder in `graph.py`.
- [x] Implement `load_config` node.
- [x] Implement `prepare_run` node.
- [x] Implement `select_repos` node.
- [x] Implement `build_tool_registry` node.
- [x] Implement sequential `inspect_repo_agent` node or loop.
- [x] Repo inspector agent must use only registered tools.
- [x] Enforce max tool calls / max iterations per repo.
- [x] Require configured-check evidence tool calls before accepting final LLM
      structured output.
- [x] Implement `normalize_agent_output` node.
- [x] Implement `merge_results` node.
- [x] Implement `summarize_with_agent` node.
- [x] Implement deterministic summary fallback for `--no-llm`.
- [x] Implement `redact_report` node.
- [x] Implement `render_markdown` node.
- [x] Implement `write_report` node.
- [ ] Implement `handle_failure` path.
- [x] Ensure graph state is serializable for tests.
- [x] Ensure one repository failure becomes a finding/incomplete result when
      possible instead of crashing the whole run.
- [x] Implement CLI:
      `langgraph-maintenance run --config examples/repos.yaml --no-llm`.
- [x] Implement CLI:
      `langgraph-maintenance run --config <config> --llm --provider openrouter`.
- [x] Add `--output-dir` option.
- [x] Add `--dry-run` option that performs checks and renders output without
      writing report files.
- [x] Ensure dry-run never sends Discord or writes reports.

Tests:

- [x] Workflow smoke test with one synthetic repo.
- [x] Workflow smoke test with two synthetic repos.
- [x] Workflow continues when one repo path is missing.
- [x] Workflow writes latest report.
- [x] Workflow dry run does not write files.
- [x] Workflow no-LLM mode requires no API key.
- [x] Workflow LLM mode uses mocked OpenRouter client.
- [x] Agent cannot call unregistered tools.
- [x] Agent tool-call limit produces incomplete check record.
- [x] Malformed agent output produces validation error and fallback/incomplete
      record.
- [ ] Fatal config failure writes/returns a useful failure result.

Validation:

- [x] `langgraph-maintenance run --config examples/repos.yaml --no-llm --dry-run`
      works.
- [x] `langgraph-maintenance run --config <temp-config> --no-llm` writes a
      report.
- [x] Mocked LLM workflow test proves repo inspector agent uses tools.
- [x] `python -m pytest` passes.

Exit criteria:

- [ ] This is the core MVP. The project is now a real tool-using LangGraph agent
      app.

### Phase 7: Safe Command Tool Execution

Goal: upgrade `run_configured_safe_command` from skipped stub to working
repo-scoped tool execution while preserving the report-only safety model.

Deliverables:

- [x] Implement command runner wrapper.
- [x] Enforce per-command timeout.
- [x] Enforce per-repo working directory.
- [x] Capture exit code.
- [x] Capture bounded stdout/stderr excerpts.
- [x] Redact command output before storing it.
- [x] Mark timeout as incomplete/skipped check with evidence.
- [x] Support command strings only from validated `safe_commands`, parsed with
      `shlex.split`, executed with `shell=False`, and restricted to narrow
      report-only diagnostic profiles.
- [x] Prefer argv/non-shell execution for internal built-in commands.
- [x] Add built-in mapping from configured checks to command labels:
      - `tests`
      - `lint`
      - `build`
      - `python-syntax`
- [x] Require a matching enabled check before any `safe_commands` label can run.
- [x] Ignore model-supplied command results unless they came from an actual
      command tool call.
- [x] If a configured check has no safe command, mark it skipped with reason.
- [x] Ensure command execution never runs fix/format/upgrade/cleanup commands.
- [x] Add optional writable temp/cache environment support outside the target
      repository for tools that need caches.

Tests:

- [x] Safe command exits `0`.
- [x] Safe command exits nonzero and becomes a finding.
- [x] Safe command timeout is reported.
- [x] Unsafe command is rejected during config validation.
- [x] Command stdout/stderr is bounded and redacted.
- [x] Missing safe command is skipped.
- [x] Working directory is the target repo.
- [x] Command runner does not mutate synthetic repo except explicitly expected
      tool cache behavior in temp dirs.
- [x] Mutating command fixtures such as `touch`, `python -c`, `ruff --fix`,
      package scripts, and git mutation commands fail config validation.
- [x] Model-fabricated command results do not enter repo results or reports.

Validation:

- [x] Synthetic config can run a harmless command such as
      `python -m pytest --version`.
- [x] Unsafe command fixtures fail before execution.

Exit criteria:

- [x] Configured tests/lint/build checks are supported without weakening the
      safety boundary, and agents can call them only through the safe command
      tool.

### Phase 8: Markdown Reporting, Redaction, And Agent Summaries

Goal: produce polished local reports from tool-using agent outputs and ensure
secret redaction is applied before persistence, model summarization, and
delivery.

Deliverables:

- [ ] Implement redaction patterns for:
      - Discord webhook URLs
      - common token/secret/password/api-key assignments
      - authorization headers
      - private key block markers
      - `.env`-style values
- [ ] Implement redaction result metadata, such as count of redactions by type.
- [ ] Redact tool outputs before they are stored, sent to summary agent, written
      to reports, or delivered.
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
- [ ] Include agent/tool-call evidence without exposing raw secrets.
- [x] Include commands run and exit statuses when command results exist.
- [x] Include skipped checks, incomplete agent runs, and auditor limitations.
- [x] Use `None found.` for empty severity sections.
- [x] Implement report writer:
      - create reports directory
      - write date report
      - avoid overwriting by using timestamp fallback
      - update `reports/latest.md`
- [x] Implement fresh failure report writer for fatal workflow errors.
- [x] Ensure failed runs never reuse stale `latest.md`.

Tests:

- [x] Redacts webhook URL.
- [x] Redacts token/password/api-key lines.
- [x] Redacts authorization headers.
- [x] Redacts private key block marker content.
- [x] Summary agent input is redacted.
- [x] Markdown renderer includes all required sections.
- [x] Empty sections use `None found.`.
- [x] Report writer updates latest report.
- [x] Report writer avoids overwriting existing report.
- [x] Failure report is fresh and does not reuse stale `latest.md`.
- [ ] Golden sample report test uses synthetic agent/tool data only.

Validation:

- [x] Generated local report for synthetic agent output is readable and
      public-safe.
- [ ] `reports/` generated files remain ignored by git.

Exit criteria:

- [x] Agentic inspection results produce polished, redacted Markdown reports.

### Phase 9: Discord Delivery

Goal: deliver a safe summary of the agent-generated report to Discord without
exposing secrets or requiring Discord for the default demo.

Deliverables:

- [x] Implement Discord sender using standard library or a minimal dependency.
- [x] Load webhook only from environment:
      - `LANGGRAPH_MAINTENANCE_DISCORD_WEBHOOK_URL`
      - fallback `DISCORD_WEBHOOK_URL`
- [ ] Support `.env` locally without committing it.
- [x] Never print webhook value.
- [x] Respect `report.discord_enabled` as the default delivery flag.
- [x] Add CLI flags to override config for a run:
      - `--send-discord`
      - `--no-discord`
- [x] Extract summary sections from full report.
- [x] Support `--summary-only`.
- [x] Support safe chunking into multiple webhook messages below Discord's
      2,000-character `content` limit.
- [x] Include chunk numbering such as `(1/3)` when more than one Discord
      message is sent.
- [x] Redact content immediately before sending.
- [ ] Include a concise note when findings came from LLM agents and may need
      human review.
- [x] Never send raw tool histories unless they have been bounded and redacted.
- [x] Handle HTTP errors with clear messages.
- [x] Add CLI command:
      `langgraph-maintenance send reports/latest.md --summary-only`.
- [x] Add optional workflow flag to send after successful run.
- [ ] Ensure failed runs send fresh failure report, not stale latest report.

Tests:

- [x] Summary extraction test.
- [x] Chunking tests for messages above 2,000 characters, preserving all
      content across multiple messages.
- [x] Config and CLI tests for Discord enabled/disabled behavior.
- [x] Missing webhook error test.
- [x] Webhook redaction test.
- [x] Mock HTTP success test.
- [x] Mock HTTP failure test.
- [ ] Fresh failure report send path test.

Validation:

- [ ] Local webhook test succeeds when `.env` is configured.
- [x] Public tests do not require a webhook.

Exit criteria:

- [x] Discord delivery is production-usable but optional.

### Phase 10: Parallel Fan-Out/Fan-In

Goal: upgrade the graph from sequential repo inspector agent runs to
portfolio-worthy parallel repository branches while preserving tool safety and
deterministic merge behavior.

Deliverables:

- [ ] Implement LangGraph fan-out over enabled repositories.
- [ ] Run one repo inspector agent branch per enabled repository.
- [ ] Keep per-repo state isolated.
- [ ] Keep per-repo tool registries isolated.
- [ ] Merge per-repo results deterministically.
- [ ] Preserve stable report ordering by config order or repo name.
- [ ] Continue when one repo fails unless marked `required`.
- [ ] Add configurable max concurrency if supported/needed.
- [ ] Add clear logs for repo agent start/end/failure.
- [ ] Preserve per-repo model/tool-call metadata.
- [ ] Ensure command timeouts still apply per repo.
- [ ] Ensure model/tool-call limits apply per repo.

Tests:

- [ ] Parallel workflow returns same normalized findings as sequential mocked
      agent workflow for synthetic repos.
- [ ] One repo failure does not prevent other repo reports.
- [ ] Required repo failure follows documented behavior.
- [ ] Report ordering is stable.
- [ ] Tool-call histories are isolated per repo.
- [ ] Parallel mocked LLM calls do not require real OpenRouter credentials.

Validation:

- [ ] Run against multiple synthetic repos.
- [ ] Run against at least one real local test repo only if public-safe and not
      committed into examples.

Exit criteria:

- [ ] LangGraph orchestration is visibly multi-agent and meaningful for
      portfolio review.

### Phase 11: Scheduling And Runtime Wrappers

Goal: make the tool-using agent usable as a scheduled local maintenance job.

Deliverables:

- [ ] Add `scripts/run_maintenance_check.sh`.
- [ ] Add `scripts/run_and_send.sh`.
- [ ] Scripts load local `.env` if present.
- [ ] Scripts enforce whole-run timeout through
      `LANGGRAPH_MAINTENANCE_TIMEOUT_SECONDS`.
- [ ] Scripts support optional OpenRouter environment variables without printing
      them:
      - `OPENROUTER_API_KEY`
      - `LANGGRAPH_MAINTENANCE_LLM_MODEL`
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
- [ ] Script logging does not print OpenRouter or Discord secrets.
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
      - OpenRouter-backed agent mode
      - optional Discord mode
      - test commands
- [ ] Expand `ARCHITECTURE.md` with:
      - graph diagram
      - node descriptions
      - state schema overview
      - supervisor/repo-inspector agent architecture
      - safe tool registry
      - deterministic safety boundary
      - safety boundary
      - failure handling
- [ ] Add `docs/portfolio-notes.md` explaining what the project demonstrates.
- [ ] Add `docs/safety.md` if not already complete.
- [ ] Add `docs/agent-tools.md` explaining each tool and its safety constraints.
- [ ] Add `docs/openrouter.md` documenting:
      - `OPENROUTER_API_KEY`
      - `LANGGRAPH_MAINTENANCE_LLM_MODEL`
      - no-LLM fallback
      - public-safe prompt/input policy
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
- [ ] No OpenRouter API keys.
- [ ] No real model account metadata.
- [ ] No private repository names or internal URLs in examples.
- [ ] No raw output copied from private repositories.
- [ ] No unredacted tool-call traces copied from private repositories.
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
