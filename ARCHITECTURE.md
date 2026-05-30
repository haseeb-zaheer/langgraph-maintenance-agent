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

## Batch 1 Boundary

Batch 1 implements only the project foundation:

- Python package metadata and CLI skeleton.
- Public-safe documentation and examples.
- Config schema and validation.
- Typed domain schemas.
- Runtime helpers for report paths and bounded output.

Batch 1 does not implement repository tools, repo inspector agents, safe command
execution, Discord delivery, systemd scheduling, OpenRouter calls, or parallel
graph execution.

## Agent Safety Boundary

Repo inspector agents will not receive raw shell access. They will call a
registry of constrained tools such as `git_status`, `list_files`,
`read_safe_file`, `search_static_markers`, `detect_dependency_manifests`, and
`run_configured_safe_command`. Tools resolve repo names through validated config,
block sensitive paths, bound outputs, and redact before content is stored or
sent back to the model.

## Source Of Truth

`PRD.md` is the main implementation reference and checklist. This architecture
document should stay aligned with the PRD when behavior or structure changes.
