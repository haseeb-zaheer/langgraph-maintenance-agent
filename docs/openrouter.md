# OpenRouter Usage

LLM mode uses OpenRouter Chat Completions directly through `httpx`.

Environment variables:

- `OPENROUTER_API_KEY`: required only for `--llm` mode.
- `LANGGRAPH_MAINTENANCE_LLM_MODEL`: optional model override.

No-LLM mode does not read or require OpenRouter credentials:

```bash
uv run langgraph-maintenance run --config examples/repos.yaml --no-llm --dry-run
```

LLM mode:

```bash
export OPENROUTER_API_KEY="sk-or-placeholder"
export LANGGRAPH_MAINTENANCE_LLM_MODEL="openrouter/model-placeholder"
uv run langgraph-maintenance run --config examples/repos.yaml --llm --provider openrouter
```

Public tests use fakes or mocked HTTP responses and never require real
credentials.
