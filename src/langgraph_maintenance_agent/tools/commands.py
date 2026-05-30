"""Configured safe command execution tool."""

from __future__ import annotations

import shlex
import subprocess
import time
from typing import Any

from langgraph_maintenance_agent.reporting.redaction import redact_text
from langgraph_maintenance_agent.schemas import CommandResult
from langgraph_maintenance_agent.tools.registry import ToolContext
from langgraph_maintenance_agent.tools.results import ToolError, ToolResult

DEFAULT_COMMAND_TIMEOUT_SECONDS = 300


def _bounded_redacted_output(text: str, max_chars: int) -> str:
    redacted = redact_text(text)
    if len(redacted) <= max_chars:
        return redacted
    return redacted[:max_chars]


def execute_configured_command(
    context: ToolContext,
    repo_name: str,
    command_label: str,
) -> CommandResult:
    """Run a validated configured command in the configured repo root."""

    repo = context.repo_config(repo_name)
    command = repo.safe_commands[command_label]
    argv = shlex.split(command)
    if not argv:
        raise ValueError("command did not parse to an argv list")
    timeout_seconds = repo.timeout_seconds or DEFAULT_COMMAND_TIMEOUT_SECONDS
    repo_root = context.repo_root(repo_name)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            cwd=repo_root,
            shell=False,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        duration = time.monotonic() - started
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        return CommandResult(
            label=command_label,
            command=argv,
            working_directory=str(repo_root),
            exit_code=None,
            timed_out=True,
            stdout_excerpt=_bounded_redacted_output(
                stdout, context.limits.max_output_chars
            ),
            stderr_excerpt=_bounded_redacted_output(
                stderr, context.limits.max_output_chars
            ),
            duration_seconds=round(duration, 3),
        )
    except OSError as exc:
        duration = time.monotonic() - started
        return CommandResult(
            label=command_label,
            command=argv,
            working_directory=str(repo_root),
            exit_code=127,
            timed_out=False,
            stdout_excerpt="",
            stderr_excerpt=_bounded_redacted_output(
                str(exc), context.limits.max_output_chars
            ),
            duration_seconds=round(duration, 3),
        )
    duration = time.monotonic() - started
    return CommandResult(
        label=command_label,
        command=argv,
        working_directory=str(repo_root),
        exit_code=completed.returncode,
        timed_out=False,
        stdout_excerpt=_bounded_redacted_output(
            completed.stdout, context.limits.max_output_chars
        ),
        stderr_excerpt=_bounded_redacted_output(
            completed.stderr, context.limits.max_output_chars
        ),
        duration_seconds=round(duration, 3),
    )


def run_configured_safe_command(
    context: ToolContext,
    repo_name: str,
    command_label: str,
) -> ToolResult:
    """Run a configured safe command and return a bounded redacted result."""

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
    try:
        argv = shlex.split(repo.safe_commands[command_label])
        if not argv:
            raise ValueError("command did not parse to an argv list")
    except ValueError as exc:
        return ToolResult(
            tool_name="run_configured_safe_command",
            repo_name=repo_name,
            ok=False,
            error=ToolError(code="invalid_command", message=str(exc)),
        )
    result = execute_configured_command(context, repo_name, command_label)
    data: dict[str, Any] = {"command_result": result.model_dump(mode="json")}
    if result.timed_out:
        data["status"] = "incomplete"
        data["reason"] = (
            f"command timed out after "
            f"{repo.timeout_seconds or DEFAULT_COMMAND_TIMEOUT_SECONDS} seconds"
        )
    else:
        data["status"] = "completed"
    return ToolResult(
        tool_name="run_configured_safe_command",
        repo_name=repo_name,
        ok=True,
        data=data,
    )
