# Routine Maintenance Agent Workflow

This document explains the intended user flow for an LLM-backed, report-only
maintenance run.

## 1. User Starts A Run

The user starts the agent manually:

```bash
langgraph-maintenance run --config config/repos.yaml --llm
```

Or a user-level systemd timer starts it on schedule.

The config is an explicit allowlist. The agent must not scan repositories that
are not listed in the config.

## 2. Agent Loads Config And Creates A Run

The workflow loads:

- configured repositories
- enabled checks
- source-review budgets
- report settings
- optional Discord delivery settings

Example source-review budget:

```yaml
source_review_max_files: 20
source_review_max_plan_files: 12
source_review_max_bytes_per_file: 12000
source_review_max_total_bytes: 80000
```

These budgets limit how much source code the agent can read. The goal is to
control private code exposure, context size, and model cost by content volume
rather than by a small arbitrary tool-call cap.

## 3. Agent Fans Out Per Repo

LangGraph starts one isolated branch per enabled repository.

Each branch gets a tool registry scoped only to that repository. A model
inspecting one repo cannot ask tools to inspect another configured repo.

## 4. Agent Collects Basic Repo Metadata

For each repo, the agent first gathers safe metadata:

- `git_status`
- `latest_commit`
- `detect_dependency_manifests`

This gives context such as current branch, dirty worktree state, latest commit,
and likely project type.

## 5. Agent Maps The Source Tree

For source review, the agent calls:

```text
summarize_source_tree(repo_name)
```

This does not dump source code. It returns bounded metadata such as:

- source roots
- detected languages
- framework signals
- test roots
- candidate source files
- generated/dependency files skipped

For a Next.js repo, candidate files may include:

```text
src/app/api/second-brain-chat/route.ts
src/app/sitemap.ts
src/app/robots.ts
src/app/articles/[slug]/page.tsx
```

## 6. Agent Lists Reviewable Source Files

The agent calls:

```text
list_source_files(repo_name)
```

The tool returns only files allowed by safety rules and budgets.

It excludes paths such as:

- `.env`
- `.next/`
- `node_modules/`
- source maps
- logs
- private keys
- build output
- binary files
- oversized files

## 7. Agent Creates A Review Plan

Before reading source code, the LLM should choose which files to inspect and
why.

Example plan:

```text
Review these files:

1. src/app/api/second-brain-chat/route.ts
   Reason: API route with request handling, rate limiting, environment usage,
   timeout handling, and backend proxying.

2. src/app/sitemap.ts
   Reason: SEO/runtime generation logic.

3. src/app/robots.ts
   Reason: crawler access logic.
```

The system should validate the plan. Paths outside the approved source list,
generated files, sensitive files, and files from other repositories must be
rejected.

## 8. Agent Reads Only Planned Files

The agent reads planned files through bounded source tools:

```text
read_source_files(repo_name, relative_paths=[...])
```

Every read is bounded, redacted, and constrained to the configured repo.

Example coverage:

```text
Read 5 files
Read 42 KB / 80 KB budget
Skipped 0 planned files
```

## 9. Agent Generates Source Findings

The LLM produces findings only from files it actually read.

Findings should cover:

- likely bugs
- refactor opportunities
- maintainability risks
- complexity or duplication hotspots
- missing validation or error handling
- missing or weak tests

Each source finding must include:

- severity
- category
- evidence path
- suggested human action

Example:

```text
Finding: In-memory rate limiting is not shared across serverless instances.
Evidence: src/app/api/second-brain-chat/route.ts
Suggested action: Use Redis/Upstash or a Vercel-compatible rate limiter.
```

## 10. System Validates Findings

Before accepting source-review findings, deterministic code should verify:

- the repo name is configured
- evidence paths are allowed
- cited source files were actually read
- generated/sensitive files are not cited
- source-review categories are valid
- every finding has a suggested action
- sensitive-looking content is redacted

Unsupported findings should be rejected or converted into incomplete-review
errors.

## 11. Agent Merges Repo Results

After all repo branches finish, LangGraph merges results in config order.

If a non-required repo fails, the run should continue and report that repo's
failure. If a required repo fails, the run should fail and write a fresh failure
report instead of sending stale output.

## 12. Agent Renders The Report

The Markdown report includes:

- Executive Summary
- Critical Findings
- High Priority
- Medium Priority
- Low Priority
- Bug Risk Review
- Refactor Opportunities
- Code Quality Notes
- Test Gap Notes
- Source review coverage
- Suggested Next Actions
- Appendix with per-repo metadata

Source review coverage should explain scan depth:

```text
Source review coverage:
- Candidate files: 47
- Planned files: 5
- Files read: 5
- Bytes read: 42 KB / 80 KB
- Generated files skipped: 312
- Source review mode: LLM semantic
```

## 13. Agent Writes The Local Report

The workflow writes a local Markdown report, for example:

```text
reports/2026-05-30-routine-maintenance.md
```

If configured, it also updates:

```text
reports/latest.md
```

## 14. Agent Optionally Sends A Discord Summary

If Discord delivery is enabled, the agent sends a redacted summary. It should
not send raw source code or large snippets.

Example summary:

```text
Routine Maintenance Report

1 repo scanned.
2 high findings.
3 medium findings.
Top issue: API route rate limiting is not production-safe on serverless.
Report path: reports/2026-05-30-routine-maintenance.md
```

## 15. User Chooses Follow-Up Fixes

The agent remains report-only. It does not edit files, run formatters, upgrade
dependencies, commit changes, reset worktrees, or delete files in target repos.

After reviewing the report, the user can ask Codex to implement selected fixes
as a separate task.
