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
