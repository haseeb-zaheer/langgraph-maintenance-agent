# OpenRouter Usage

LLM mode uses OpenRouter Chat Completions directly through `httpx`.

Environment variables:

- `OPENROUTER_API_KEY`: required only for `--llm` mode.
- `LANGGRAPH_MAINTENANCE_LLM_MODEL`: optional model override. Defaults to
  `deepseek/deepseek-v4-flash`.

No-LLM mode does not read or require OpenRouter credentials:

```bash
uv run langgraph-maintenance run --config examples/repos.yaml --no-llm --dry-run
```

LLM mode:

```bash
export OPENROUTER_API_KEY="sk-or-placeholder"
export LANGGRAPH_MAINTENANCE_LLM_MODEL="deepseek/deepseek-v4-flash"
uv run langgraph-maintenance run --config examples/repos.yaml --llm --provider openrouter
```

The default model is DeepSeek V4 Flash because it is cost-efficient and
positioned for responsive coding and agent workflows on OpenRouter. The repo
inspector requests required tool use until configured-check evidence has been
collected, then accepts final structured JSON.

When `--llm` is enabled, the workflow also asks a summary agent for structured
`SummaryOutput` after repository results have been redacted. If the summary
model call fails or returns malformed JSON, the workflow records a recoverable
error and uses the deterministic summary fallback. `--no-llm` never calls the
summary agent.

Public tests use fakes or mocked HTTP responses and never require real
credentials.
