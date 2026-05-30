"""Configured safe command tool placeholder."""

from __future__ import annotations

from langgraph_maintenance_agent.tools.registry import ToolContext
from langgraph_maintenance_agent.tools.results import ToolError, ToolResult


def run_configured_safe_command(
    context: ToolContext,
    repo_name: str,
    command_label: str,
) -> ToolResult:
    """Return a skipped result until safe command execution is implemented."""

    try:
        repo = context.repo_config(repo_name)
    except KeyError as exc:
        return ToolResult(
            tool_name="run_configured_safe_command",
            repo_name=repo_name,
            ok=False,
            error=ToolError(code="unknown_repo", message=str(exc)),
        )
    if command_label not in repo.safe_commands:
        return ToolResult(
            tool_name="run_configured_safe_command",
            repo_name=repo_name,
            ok=False,
            error=ToolError(
                code="unknown_command_label", message="command label is not configured"
            ),
        )
    return ToolResult(
        tool_name="run_configured_safe_command",
        repo_name=repo_name,
        ok=True,
        data={
            "status": "skipped",
            "reason": "safe command execution is reserved for a later batch",
            "command_label": command_label,
        },
    )
