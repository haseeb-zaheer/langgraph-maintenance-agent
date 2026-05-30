# Agent Tool Safety

Repository inspector agents can call only the registered Python tools created
from validated config. Every tool takes `repo_name`; no tool accepts arbitrary
repository roots from the model. During an individual repo inspection, tool calls
for any other repo are rejected.

Current tools:

- `git_status(repo_name)`: branch, dirty state, ahead/behind where available.
- `latest_commit(repo_name)`: latest hash, commit date, and subject.
- `list_files(repo_name, patterns=None)`: bounded public-safe relative paths.
- `read_safe_file(repo_name, relative_path)`: approved small text docs and
  manifests only.
- `summarize_source_tree(repo_name)`: bounded source roots, language counts,
  framework signals, test roots, and review candidates.
- `list_source_files(repo_name, patterns=None)`: bounded Python and
  JavaScript/TypeScript source files approved for semantic review.
- `read_source_file(repo_name, relative_path)`: one approved source file,
  bounded by repo source-review budgets and redacted before model/state use.
- `search_static_markers(repo_name)`: bounded TODO/FIXME/HACK summaries.
- `detect_dependency_manifests(repo_name)`: Python, Node, Docker, and dbt
  manifests without running package managers.
- `run_configured_safe_command(repo_name, command_label)`: executes only a
  matching enabled-check command from the current repo's validated
  `safe_commands`.

Blocked paths include `.env`, logs, databases, private keys, generated reports,
caches, generated artifacts, dependency folders, symlinks, path traversal, files
outside the repo, oversized files, and likely binary files. Generated artifacts
include `.next/`, source maps, coverage output, `dist/`, `build/`, caches,
vendored directories, and minified bundles. Traversal prunes blocked
directories before descending. Tool outputs are JSON-serializable and bounded
before they can be returned to an LLM.

In LLM mode, configured checks define required evidence tools. The repo
inspector asks OpenRouter for required tool use until those tools complete, and
does not accept final structured findings before evidence exists.
For source-review checks, required evidence includes source tree summary,
source file listing, and at least one bounded source file read. Source-review
findings must cite evidence paths and suggested human actions. No-LLM mode
records semantic source review as skipped instead of fabricating findings.

In the parallel workflow, each repo branch receives a separate registry built
from a one-repo config. OpenRouter tool schemas therefore enumerate only the
current repo name for `repo_name`. Reports include concise tool-call metadata in
the appendix, limited to tool name, status, argument names, counts, and error
codes. Raw tool results and full argument payloads are not rendered as tool
history.

## Configured Command Tool

`run_configured_safe_command` is the only command-execution surface. It does not
accept arbitrary command strings from the model; it accepts a `command_label`,
looks that label up in the current repo config, parses the configured string
with `shlex.split`, verifies it against a narrow report-only diagnostic profile,
and runs it with `shell=False` in the configured repo root. Supported temp/cache
environment variables are redirected outside the target repo.

Command behavior:

- Unknown repo names return `unknown_repo`.
- Unknown labels return `unknown_command_label` and do not execute anything.
- Labels not enabled by configured checks return `command_not_enabled`.
- Invalid or disallowed command strings return `invalid_command`.
- Timeouts return `ok=True` with `status: incomplete`, a timed-out
  `CommandResult`, and any bounded redacted output captured before timeout.
- Nonzero exits return `ok=True` with a `CommandResult`; repo inspection turns
  them into medium-severity findings that need human review.
- Stdout and stderr excerpts are redacted and bounded by
  `ToolLimits.max_output_chars` before entering tool results, graph state,
  report rendering, or model messages.
- LLM-mode reports keep command results only when they were produced by actual
  command tool calls.

Allowed profiles:

- `tests`: `pytest ...` or `python -m pytest ...`
- `lint`: `ruff check ...` without fix flags
- `python-syntax`: `python -m compileall ...` or `python -m py_compile ...`
- `build`: `python -m build ...`

The deterministic no-LLM fallback maps command-style checks to labels:

- `tests` -> `tests`
- `lint` -> `lint`
- `build` -> `build`
- `python-syntax` -> `python-syntax`

If one of those checks is enabled but the matching `safe_commands` label is not
configured, the inspector records a skipped check with a clear reason.
