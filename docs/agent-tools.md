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
- `search_static_markers(repo_name)`: bounded TODO/FIXME/HACK summaries.
- `detect_dependency_manifests(repo_name)`: Python, Node, Docker, and dbt
  manifests without running package managers.
- `run_configured_safe_command(repo_name, command_label)`: executes only a
  matching command from the current repo's validated `safe_commands`.

Blocked paths include `.env`, logs, databases, private keys, generated reports,
caches, symlinks, path traversal, files outside the repo, oversized files, and
likely binary files. Traversal prunes blocked directories before descending.
Tool outputs are JSON-serializable and bounded before they can be returned to an
LLM.

## Configured Command Tool

`run_configured_safe_command` is the only command-execution surface. It does not
accept arbitrary command strings from the model; it accepts a `command_label`,
looks that label up in the current repo config, parses the configured string
with `shlex.split`, and runs it with `shell=False` in the configured repo root.

Command behavior:

- Unknown repo names return `unknown_repo`.
- Unknown labels return `unknown_command_label` and do not execute anything.
- Invalid command strings that cannot be parsed return `invalid_command`.
- Timeouts return `ok=True` with `status: incomplete`, a timed-out
  `CommandResult`, and any bounded redacted output captured before timeout.
- Nonzero exits return `ok=True` with a `CommandResult`; repo inspection turns
  them into medium-severity findings that need human review.
- Stdout and stderr excerpts are redacted and bounded by
  `ToolLimits.max_output_chars` before entering tool results, graph state,
  report rendering, or model messages.

The deterministic no-LLM fallback maps command-style checks to labels:

- `tests` -> `tests`
- `lint` -> `lint`
- `build` -> `build`
- `python-syntax` -> `python-syntax`

If one of those checks is enabled but the matching `safe_commands` label is not
configured, the inspector records a skipped check with a clear reason.
