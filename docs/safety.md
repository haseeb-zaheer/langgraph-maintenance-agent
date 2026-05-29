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
- Run only configured safe commands once that phase is implemented.

## Batch 1 Scope

Batch 1 implements project foundation, config validation, schemas, and runtime
helpers. It does not inspect target repositories or send reports.

