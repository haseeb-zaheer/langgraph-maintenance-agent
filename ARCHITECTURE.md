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

## Batch 3 Implementation

Batch 3 implements the first tool-using agent workflow plus bounded configured
command execution:

- `tools/` exposes repo-scoped read-only tools and OpenRouter-compatible tool
  schemas.
- `llm/openrouter.py` provides a direct non-streaming Chat Completions client
  with tool-call parsing and JSON-schema response format support.
- `agents/repo_inspector.py` runs an OpenRouter-backed tool loop or a
  deterministic no-LLM fallback. In no-LLM mode, configured command-style
  checks map to `safe_commands` labels for `tests`, `lint`, `build`, and
  `python-syntax`.
- `tools/commands.py` executes only commands explicitly configured for the
  current repo. Commands are parsed with `shlex.split`, run with `shell=False`,
  use the configured repo path as `cwd`, enforce `timeout_seconds` or a
  300-second default, and return bounded redacted stdout/stderr excerpts.
- `graph.py` assembles the sequential supervisor workflow:
  `load_config -> prepare_run -> select_repos -> build_tool_registry ->
  inspect_repo_agent -> normalize_agent_output -> merge_results ->
  summarize_with_agent -> render_markdown -> redact_report -> write_report`.

## Remaining Boundary

Later batches still own production report polish, redaction metadata, Discord
delivery, parallel fan-out, wrapper scripts, optional temp/cache isolation for
commands that need writable caches, and the systemd timer.

## Agent Safety Boundary

Repo inspector agents do not receive raw shell access. They call a registry of
constrained tools such as `git_status`, `list_files`, `read_safe_file`,
`search_static_markers`, `detect_dependency_manifests`, and
`run_configured_safe_command`. Tools resolve repo names through validated config,
block sensitive paths, bound outputs, and redact before content is stored or sent
back to the model. File traversal skips symlinks and prunes blocked runtime or
dependency directories. Each inspector run rejects model tool calls or final
structured output that tries to switch to a different configured repository.

`run_configured_safe_command` is a deterministic safety-boundary tool rather
than raw shell access. The model can supply only `repo_name` and
`command_label`; the actual command string comes from validated config for that
repo. Unknown labels return a safe tool error. Timed-out commands return a
successful tool envelope with a timed-out `CommandResult` and an incomplete
reason. Nonzero exits are preserved as command results and normalized into
findings by the inspector/reporting path.

## Source Of Truth

`PRD.md` is the main implementation reference and checklist. This architecture
document should stay aligned with the PRD when behavior or structure changes.
