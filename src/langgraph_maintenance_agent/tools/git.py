"""Read-only git repository tools."""

from __future__ import annotations

import subprocess

from langgraph_maintenance_agent.runtime.text import bound_text
from langgraph_maintenance_agent.tools.registry import ToolContext
from langgraph_maintenance_agent.tools.results import ToolError, ToolResult


def _git(
    context: ToolContext, repo_name: str, args: list[str]
) -> subprocess.CompletedProcess[str]:
    root = context.repo_root(repo_name)
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def git_status(context: ToolContext, repo_name: str) -> ToolResult:
    """Return concise branch and dirty state metadata."""

    try:
        branch = _git(context, repo_name, ["rev-parse", "--abbrev-ref", "HEAD"])
        status = _git(context, repo_name, ["status", "--short", "--branch"])
        ahead_behind = _git(
            context,
            repo_name,
            ["rev-list", "--left-right", "--count", "HEAD...@{upstream}"],
        )
    except (OSError, subprocess.TimeoutExpired, KeyError) as exc:
        return ToolResult(
            tool_name="git_status",
            repo_name=repo_name,
            ok=False,
            error=ToolError(code="git_status_failed", message=str(exc)),
        )
    if status.returncode != 0:
        return ToolResult(
            tool_name="git_status",
            repo_name=repo_name,
            ok=False,
            error=ToolError(
                code="not_git_repo", message=bound_text(status.stderr, 500)
            ),
        )
    lines = status.stdout.splitlines()
    changed = [line for line in lines if not line.startswith("##")]
    ahead = None
    behind = None
    if ahead_behind.returncode == 0:
        ahead_text, behind_text = (ahead_behind.stdout.strip().split() + ["0", "0"])[
            :2
        ]
        ahead = int(ahead_text)
        behind = int(behind_text)
    return ToolResult(
        tool_name="git_status",
        repo_name=repo_name,
        ok=True,
        data={
            "branch": branch.stdout.strip() if branch.returncode == 0 else None,
            "dirty": bool(changed),
            "changed_count": len(changed),
            "ahead": ahead,
            "behind": behind,
            "status_excerpt": bound_text(
                status.stdout, context.limits.max_output_chars
            ),
        },
    )


def latest_commit(context: ToolContext, repo_name: str) -> ToolResult:
    """Return latest commit hash, ISO date, and subject."""

    try:
        result = _git(context, repo_name, ["log", "-1", "--format=%H%x00%cI%x00%s"])
    except (OSError, subprocess.TimeoutExpired, KeyError) as exc:
        return ToolResult(
            tool_name="latest_commit",
            repo_name=repo_name,
            ok=False,
            error=ToolError(code="latest_commit_failed", message=str(exc)),
        )
    if result.returncode != 0:
        return ToolResult(
            tool_name="latest_commit",
            repo_name=repo_name,
            ok=False,
            error=ToolError(
                code="latest_commit_unavailable", message=bound_text(result.stderr, 500)
            ),
        )
    commit_hash, commit_date, subject = (
        result.stdout.rstrip("\n").split("\x00") + ["", "", ""]
    )[:3]
    return ToolResult(
        tool_name="latest_commit",
        repo_name=repo_name,
        ok=True,
        data={"hash": commit_hash, "date": commit_date, "subject": subject},
    )
