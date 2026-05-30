# Routine Maintenance Report - 2026-01-01

## Executive Summary

Synthetic sample report for public documentation. No real repositories were
scanned for this example.

## Critical Findings

None found.

## High Priority

None found.

## Medium Priority

- `example-python-service`: documentation is missing an architecture overview.

## Low Priority

- `example-python-service`: one TODO marker was found in a synthetic fixture.

## Repositories Scanned

- `example-python-service`: `/path/to/example-python-service`

## Repositories Skipped

None found.

## Dependency Concerns

None found.

## Bug Risk Review

- `example-python-service`: synthetic input validation risk in `src/example.py`.

## Refactor Opportunities

- `example-python-service`: synthetic repeated parsing logic in `src/parser.py`.

## Code Quality Notes

None found.

## Test Gap Notes

- `example-python-service`: synthetic edge case lacks focused coverage in
  `tests/test_parser.py`.

## Source Review Coverage

### `example-python-service`

- Candidate files: 4
- Planned files: 2
- Files read: 2
- Bytes read: 4096
- Skipped planned files: 0
- Generated files skipped: 3
- Review mode: `llm-planned`
- Plan rationale: Synthetic API and parser files were highest-signal examples.
- Planned paths: `src/api.py`, `src/parser.py`
- Read paths: `src/api.py`, `src/parser.py`

## Test/Lint/Build Results

None found.

## Command Results

None found.

## Dirty Worktrees

None found.

## Suggested Next Actions

- Add an architecture overview to the synthetic example service.

## Appendix: Per-Repo Details

This report is synthetic and safe to commit.
