# Safety Notes

This repository is designed to be public. All examples, tests, fixtures, and
documentation must stay public-safe.

## Public Repository Rules

- Do not commit `.env` files.
- Do not commit real Discord webhook URLs.
- Do not commit API keys, tokens, passwords, authorization headers, or private
  key material.
- Do not commit raw logs or generated private reports.
- Do not include private repository paths unless they are already public-safe.
- Use synthetic paths and synthetic findings in examples.

## Agent Operating Rules

- Scan only repositories explicitly configured in the allowlist.
- Do not infer sibling repositories from a parent folder.
- Preserve dirty worktrees in target repositories.
- Report findings; do not automatically fix them.
- Do not run formatters, fix commands, migrations, upgrades, cleanup commands,
  or git mutation commands in target repositories.
- Run only explicitly configured safe commands for the current repo when the
  matching check is enabled.

## Configured Commands

Configured commands are report-only diagnostics. The model can request
`run_configured_safe_command(repo_name, command_label)`, but it cannot provide a
raw command string. The command string comes from validated config for that repo,
is parsed with `shlex.split`, must match an approved diagnostic profile, and is
executed with `shell=False` in the configured repo root. Supported temp/cache
environment variables point outside the target repo.

Command output is bounded and redacted before it enters tool results, workflow
state, report rendering, or model messages. Unknown labels and unparsable
commands do not execute. Commands such as `python -c`, package-manager scripts,
formatter/fixer invocations, git mutation commands, and ad hoc file writes fail
config validation. Timeouts and nonzero exits are reported for human review; the
agent does not clean, reset, fix, upgrade, or rewrite the target repository
after a command result.

## Discord Delivery

Discord delivery is opt-in and disabled by default. Webhook URLs come from
environment variables, never committed config, and are not printed in CLI output
or reports. The routine-specific
`LANGGRAPH_MAINTENANCE_DISCORD_WEBHOOK_URL` takes precedence over the fallback
`DISCORD_WEBHOOK_URL`.

Before sending, content is redacted again. Full-report sends are split into
multiple webhook messages when needed so every Discord `content` payload stays
below the 2,000-character message limit. Multi-message sends use chunk prefixes
such as `(1/3)`.

Failed runs write a fresh failure report and do not update or send stale
`reports/latest.md`.

## Runtime Scripts And Systemd

`scripts/run_maintenance_check.sh` and `scripts/run_and_send.sh` load local
`.env` with shell export mode and never echo environment values. Keep
OpenRouter keys and Discord webhooks in local environment only. The scripts
default to no-LLM mode; set `LANGGRAPH_MAINTENANCE_USE_LLM=1` only when local
OpenRouter credentials are configured.

`LANGGRAPH_MAINTENANCE_TIMEOUT_SECONDS` enforces a whole-run timeout. If the
wrapper itself times out or fails before the Python workflow can finish, it
writes a fresh timestamped failure report under `reports/` and exits nonzero.
`run_and_send.sh` performs Discord delivery only inside a successful workflow
run, so timeout and failure paths do not send stale `reports/latest.md`.

The user-level systemd service reads `.env` through `EnvironmentFile=-...` and
executes `scripts/run_and_send.sh`. The timer uses
`OnCalendar=*-*-* 11:00:00` with `Persistent=true`.
