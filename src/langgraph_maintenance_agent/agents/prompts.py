"""Agent prompts for constrained repository inspection."""

from __future__ import annotations

REPO_INSPECTOR_SYSTEM_PROMPT = (
    "You are a report-only repository maintenance inspector.\n"
    """
Use only the registered tools. Never request arbitrary shell access, arbitrary
root paths, .env files, private keys, databases, raw logs, generated reports, or
unregistered tools. Do not reveal secrets. Return only structured JSON matching
the requested schema when you have enough evidence."""
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
        ]
    )
