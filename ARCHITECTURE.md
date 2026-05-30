# LangGraph Routine Maintenance Agent Architecture

## Overview

The project is a workflow-first LangGraph application. Deterministic Python code
handles configuration, validation, repository metadata, redaction, report
rendering, and delivery mechanics. LLM calls are reserved for later optional
summarization and prioritization over already structured findings.

## Target Flow

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

## Batch 1 Boundary

Batch 1 implements only the project foundation:

- Python package metadata and CLI skeleton.
- Public-safe documentation and examples.
- Config schema and validation.
- Typed domain schemas.
- Runtime helpers for report paths and bounded output.

Batch 1 does not implement repository scanning, safe command execution,
Discord delivery, systemd scheduling, optional LLM calls, or parallel graph
execution.

## Source Of Truth

`PRD.md` is the main implementation reference and checklist. This architecture
document should stay aligned with the PRD when behavior or structure changes.
