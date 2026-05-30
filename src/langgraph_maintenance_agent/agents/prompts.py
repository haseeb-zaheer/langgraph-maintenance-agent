"""Agent prompts for constrained repository inspection."""

from __future__ import annotations

REPO_INSPECTOR_SYSTEM_PROMPT = (
    "You are a report-only repository maintenance inspector.\n"
    """
Use only the registered tools. Never request arbitrary shell access, arbitrary
root paths, .env files, private keys, databases, raw logs, generated reports, or
unregistered tools. Do not reveal secrets. For source-code review, read only
bounded files through registered source tools and cite concise evidence paths.
Return only structured JSON matching the requested schema when you have enough
evidence."""
)

SUMMARY_SYSTEM_PROMPT = (
    "You summarize already-redacted routine maintenance findings.\n"
    """
Use only the provided redacted structured data. Do not invent repositories,
commands, credentials, or findings. Return concise structured JSON matching the
requested schema."""
)

SOURCE_REVIEW_PLANNER_SYSTEM_PROMPT = (
    "You create report-only source review plans from metadata.\n"
    """
Use only the provided source tree and ranked candidate metadata. Do not request
source reads, shell access, arbitrary paths, generated files, secrets, or
unregistered tools. Select a small set of high-priority listed candidate paths
and explain why each file should be reviewed. Return only structured JSON
matching the requested schema."""
)

SOURCE_REVIEW_FINDINGS_SYSTEM_PROMPT = (
    "You produce source-review findings from already-read evidence.\n"
    """
Use only the validated plan and redacted file contents provided. Do not cite
unread files. Do not include source snippets. Findings must be report-only and
use only bug-risk, refactor, code-quality, or test-gap categories with suggested
human actions. Return only structured JSON matching the requested schema."""
)


def repo_inspector_user_prompt(
    *,
    repo_name: str,
    checks: list[str],
    safe_command_labels: list[str],
    notes: str | None,
) -> str:
    """Build the per-repository inspector prompt."""

    return "\n".join(
        [
            f"Inspect configured repo: {repo_name}",
            f"Enabled checks: {', '.join(checks) if checks else 'none'}",
            "Allowed command labels: "
            f"{', '.join(safe_command_labels) if safe_command_labels else 'none'}",
            f"Notes: {notes or 'none'}",
            "Produce concise actionable findings grouped by severity.",
            "For source-review checks, look for likely bugs, refactor "
            "opportunities, complexity or duplication hotspots, validation and "
            "error-handling gaps, and missing or weak tests. Source-review "
            "findings must include evidence paths and suggested human actions.",
        ]
    )


def source_review_planner_user_prompt(
    *,
    repo_name: str,
    max_plan_files: int,
    source_metadata: str,
) -> str:
    """Build the staged source-review planning prompt."""

    return "\n".join(
        [
            f"Plan a source review for configured repo: {repo_name}",
            f"Maximum files to plan: {max_plan_files}",
            "Select only paths present in ranked_candidates/candidate_files.",
            "Prefer API routes, request/response handling, auth, rate limiting, "
            "environment handling, network calls, filesystem use, runtime glue, "
            "and risky source files without nearby tests.",
            source_metadata,
        ]
    )


def source_review_findings_user_prompt(
    *,
    repo_name: str,
    plan_and_evidence: str,
) -> str:
    """Build the final staged source-review findings prompt."""

    return "\n".join(
        [
            f"Generate source-review findings for configured repo: {repo_name}",
            "Use only the read source evidence and source-tree/test metadata in "
            "this payload. If there are no concrete findings, return an empty "
            "findings list and concise summary.",
            plan_and_evidence,
        ]
    )


def source_review_repair_user_prompt(
    *,
    repo_name: str,
    validation_error: str,
    allowed_read_paths: list[str],
    allowed_metadata_paths: list[str],
    original_output: str,
) -> str:
    """Build the one-shot source-review repair prompt."""

    return "\n".join(
        [
            f"Repair source-review findings for configured repo: {repo_name}",
            "Return corrected structured JSON only.",
            "Do not request shell access, file access, source reads, generated "
            "files, secrets, or unregistered tools.",
            "Do not introduce new evidence paths.",
            f"Validation error: {validation_error}",
            "Allowed read evidence paths for non-test-gap findings: "
            + (", ".join(allowed_read_paths) if allowed_read_paths else "none"),
            "Allowed metadata paths for test-gap findings: "
            + (
                ", ".join(allowed_metadata_paths)
                if allowed_metadata_paths
                else "none"
            ),
            "Original rejected output, already redacted:",
            original_output,
        ]
    )


def summary_user_prompt(*, redacted_payload: str) -> str:
    """Build the cross-repository summary prompt."""

    return "\n".join(
        [
            "Create an executive summary and suggested next actions for this "
            "maintenance run.",
            "The payload below has already been redacted; do not ask for raw "
            "logs or secrets.",
            redacted_payload,
        ]
    )
