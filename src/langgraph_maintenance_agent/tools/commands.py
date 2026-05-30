"""Configured safe command execution tool."""

from __future__ import annotations

import subprocess
import time
from typing import Any

from langgraph_maintenance_agent.config import (
    SafeCommandPolicyError,
    allowed_command_labels,
    parse_safe_command,
    validate_safe_command_profile,
)
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
    argv = validate_safe_command_profile(command_label, command)
    timeout_seconds = repo.timeout_seconds or DEFAULT_COMMAND_TIMEOUT_SECONDS
    repo_root = context.repo_root(repo_name)
    started = time.monotonic()
    command_env = command_environment()
    runtime_argv = command_runtime_argv(command_label, argv)
    try:
        completed = subprocess.run(
            runtime_argv,
            cwd=repo_root,
            env=command_env,
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
            command=runtime_argv,
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
            timeout_seconds=timeout_seconds,
        )
    except OSError as exc:
        duration = time.monotonic() - started
        return CommandResult(
            label=command_label,
            command=runtime_argv,
            working_directory=str(repo_root),
            exit_code=127,
            timed_out=False,
            stdout_excerpt="",
            stderr_excerpt=_bounded_redacted_output(
                str(exc), context.limits.max_output_chars
            ),
            duration_seconds=round(duration, 3),
            timeout_seconds=timeout_seconds,
        )
    duration = time.monotonic() - started
    return CommandResult(
        label=command_label,
        command=runtime_argv,
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
        timeout_seconds=timeout_seconds,
    )


def command_environment() -> dict[str, str]:
    """Return environment overrides that keep caches outside target repos."""

    import os
    import tempfile

    env = os.environ.copy()
    temp_root = tempfile.gettempdir()
    cache_dir = os.path.join(temp_root, "langgraph-maintenance-agent-cache")
    pycache_dir = os.path.join(temp_root, "langgraph-maintenance-agent-pycache")
    os.makedirs(cache_dir, exist_ok=True)
    os.makedirs(pycache_dir, exist_ok=True)
    env.update(
        {
            "TMPDIR": temp_root,
            "TEMP": temp_root,
            "TMP": temp_root,
            "XDG_CACHE_HOME": cache_dir,
            "RUFF_NO_CACHE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPYCACHEPREFIX": pycache_dir,
        }
    )
    return env


def command_runtime_argv(command_label: str, argv: list[str]) -> list[str]:
    """Return argv with target-repo writes redirected where supported."""

    if command_label != "build" or "--outdir" in argv:
        return argv
    import os
    import tempfile

    build_dir = os.path.join(tempfile.gettempdir(), "langgraph-maintenance-agent-build")
    os.makedirs(build_dir, exist_ok=True)
    return [*argv, "--outdir", build_dir]


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
    if command_label not in allowed_command_labels(repo.checks):
        return ToolResult(
            tool_name="run_configured_safe_command",
            repo_name=repo_name,
            ok=False,
            error=ToolError(
                code="command_not_enabled",
                message="command label is not enabled by configured checks",
            ),
        )
    try:
        parse_safe_command(repo.safe_commands[command_label])
        validate_safe_command_profile(command_label, repo.safe_commands[command_label])
    except SafeCommandPolicyError as exc:
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
