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
  framework signals, test roots, generated-file skip counts, and ranked review
  candidates.
- `list_source_files(repo_name, patterns=None)`: bounded Python and
  JavaScript/TypeScript source files approved for semantic review, ranked with
  source-review signals and nearby-test metadata.
- `read_source_file(repo_name, relative_path)`: one approved source file,
  bounded by repo source-review budgets and redacted before model/state use.
- `read_source_files(repo_name, relative_paths)`: batch-read planned source
  files, returning independent read/skipped metadata so one bad planned path
  does not fail the whole batch.
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

In LLM mode, configured checks define required evidence. Generic repository
checks use constrained tool calls before final structured findings are accepted.
Source-review checks use a deterministic staged workflow:

1. map the source tree with `summarize_source_tree`
2. list and rank approved candidates with `list_source_files`
3. ask the model for a structured `SourceReviewPlan`
4. validate planned paths against approved candidates
5. batch-read only planned files through `read_source_files`
6. ask the model for strict source-review findings from the validated plan and
   read evidence
7. make one repair attempt if the output is malformed, missing required
   evidence, or cites unread evidence
8. reject findings that still cite unread or unapproved evidence paths

Source-review findings must use `bug-risk`, `refactor`, `code-quality`, or
`test-gap`, cite non-empty evidence paths, and include non-empty suggested
human actions. Test-gap findings may cite source-tree/test-root metadata; other
source findings must cite files that were actually read. Repair prompts include
only the validation error, allowed paths, and redacted rejected output; they do
not request shell access, arbitrary files, or additional source reads. No-LLM
mode records semantic source review as skipped instead of fabricating findings.

Candidate ranking is heuristic. It prioritizes Next.js API routes and route
handlers, auth, rate-limit, request/response, environment, fetch/network,
filesystem, sitemap, robots, runtime glue, and risky source files without
nearby tests. CSS, simple page/layout files, test files, generated artifacts,
source maps, caches, and dependency output are de-emphasized or excluded.

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
