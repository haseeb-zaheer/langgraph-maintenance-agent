"""Sequential tool-using repository inspector agent."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from langgraph_maintenance_agent.agents.prompts import (
    REPO_INSPECTOR_SYSTEM_PROMPT,
    repo_inspector_user_prompt,
)
from langgraph_maintenance_agent.config import (
    COMMAND_CHECK_LABELS,
    CheckName,
    RepoConfig,
    allowed_command_labels,
)
from langgraph_maintenance_agent.llm.openrouter import OpenRouterClient
from langgraph_maintenance_agent.schemas import (
    AgentError,
    CommandResult,
    Finding,
    FindingCategory,
    IncompleteAgentRun,
    RepoInspectorOutput,
    RepoResult,
    Severity,
    SkippedCheck,
)
from langgraph_maintenance_agent.tools.registry import ToolRegistry
from langgraph_maintenance_agent.tools.results import ToolCallRecord, ToolResult

COMMAND_LABEL_CATEGORIES: dict[str, FindingCategory] = {
    "tests": FindingCategory.TEST,
    "lint": FindingCategory.STATIC,
    "build": FindingCategory.BUILD,
    "python-syntax": FindingCategory.TEST,
}


def incomplete_to_repo_result(incomplete: IncompleteAgentRun) -> RepoResult:
    """Convert an incomplete agent run to a repo result with a recoverable error."""

    return RepoResult(
        repo_name=incomplete.repo_name,
        errors=[
            AgentError(
                message=incomplete.reason,
                repo_name=incomplete.repo_name,
                stage=incomplete.stage,
                recoverable=True,
            )
        ],
    )


class RepoInspectorAgent:
    """Tool-using repo inspector with deterministic fallback."""

    def __init__(
        self,
        *,
        tool_registry: ToolRegistry,
        llm_client: OpenRouterClient | None = None,
        max_tool_calls: int = 12,
        max_iterations: int = 6,
    ) -> None:
        self.tool_registry = tool_registry
        self.llm_client = llm_client
        self.max_tool_calls = max_tool_calls
        self.max_iterations = max_iterations

    def inspect(self, repo: RepoConfig) -> RepoResult:
        """Inspect a repo using LLM tool calls or deterministic fallback."""

        if self.llm_client is None:
            return self.inspect_without_llm(repo)
        return self.inspect_with_llm(repo)

    def inspect_without_llm(self, repo: RepoConfig) -> RepoResult:
        """Run a fixed safe tool sequence without model credentials."""

        tool_calls: list[ToolCallRecord] = []

        def call(name: str, args: dict[str, Any]) -> ToolResult:
            result = self.tool_registry.call(name, args)
            tool_calls.append(
                ToolCallRecord(
                    tool_name=name,
                    repo_name=repo.name,
                    arguments=args,
                    status="completed" if result.ok else "failed",
                    result=result,
                )
            )
            return result

        results = [
            call("git_status", {"repo_name": repo.name}),
            call("latest_commit", {"repo_name": repo.name}),
            call("list_files", {"repo_name": repo.name}),
            call("search_static_markers", {"repo_name": repo.name}),
            call("detect_dependency_manifests", {"repo_name": repo.name}),
        ]
        findings: list[Finding] = []
        skipped = [
            SkippedCheck(
                repo_name=repo.name,
                check_name="llm-inspection",
                reason="No-LLM mode used deterministic safe tool fallback.",
            )
        ]
        for result in results:
            if not result.ok and result.error is not None:
                findings.append(
                    Finding(
                        repo_name=repo.name,
                        severity=Severity.LOW,
                        category=FindingCategory.RUNTIME,
                        title=f"{result.tool_name} did not complete",
                        description=result.error.message,
                        needs_human_review=True,
                    )
                )
        marker_result = next(
            (
                result
                for result in results
                if result.tool_name == "search_static_markers"
            ),
            None,
        )
        if marker_result and marker_result.ok and marker_result.data.get("matches"):
            matches = marker_result.data["matches"]
            findings.append(
                Finding(
                    repo_name=repo.name,
                    severity=Severity.INFO,
                    category=FindingCategory.STATIC,
                    title="Static maintenance markers found",
                    description=f"Found {len(matches)} TODO/FIXME/HACK markers.",
                    evidence_paths=sorted({match["path"] for match in matches})[:10],
                    suggested_action=(
                        "Review the listed markers during routine maintenance."
                    ),
                )
            )
        command_results: list[CommandResult] = []
        for check, label in COMMAND_CHECK_LABELS.items():
            if check not in repo.checks:
                continue
            if label not in repo.safe_commands:
                skipped.append(
                    SkippedCheck(
                        repo_name=repo.name,
                        check_name=check.value,
                        reason=(
                            "No safe_commands entry configured for label "
                            f"`{label}`."
                        ),
                    )
                )
                continue
            command_tool_result = call(
                "run_configured_safe_command",
                {"repo_name": repo.name, "command_label": label},
            )
            if command_tool_result.ok and "command_result" in command_tool_result.data:
                command_result = CommandResult.model_validate(
                    command_tool_result.data["command_result"]
                )
                command_results.append(command_result)
                findings.extend(command_result_findings(repo.name, command_result))
                if command_result.timed_out:
                    skipped.append(
                        SkippedCheck(
                            repo_name=repo.name,
                            check_name=label,
                            reason=str(
                                command_tool_result.data.get(
                                    "reason", "safe command did not complete"
                                )
                            ),
                        )
                    )
            elif command_tool_result.error is not None:
                findings.append(
                    Finding(
                        repo_name=repo.name,
                        severity=Severity.LOW,
                        category=FindingCategory.RUNTIME,
                        title=f"{label} command did not complete",
                        description=command_tool_result.error.message,
                        command_label=label,
                        needs_human_review=True,
                    )
                )
        return RepoResult(
            repo_name=repo.name,
            path=str(repo.path) if repo.path is not None else None,
            findings=findings,
            skipped_checks=skipped,
            command_results=command_results,
        )

    def inspect_with_llm(self, repo: RepoConfig) -> RepoResult:
        """Run the OpenRouter-backed tool loop."""

        assert self.llm_client is not None
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": REPO_INSPECTOR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": repo_inspector_user_prompt(
                    repo_name=repo.name,
                    checks=[check.value for check in repo.checks],
                    safe_command_labels=sorted(
                        set(repo.safe_commands) & allowed_command_labels(repo.checks)
                    ),
                    notes=repo.notes,
                ),
            },
        ]
        executed_command_results: list[CommandResult] = []
        tool_calls_made = 0
        for iteration in range(1, self.max_iterations + 1):
            try:
                response = self.llm_client.chat(
                    messages=messages,
                    tools=self.tool_registry.schemas(),
                    response_schema=RepoInspectorOutput.model_json_schema(),
                )
            except Exception as exc:
                return incomplete_to_repo_result(
                    IncompleteAgentRun(
                        repo_name=repo.name,
                        reason=str(exc),
                        stage="model_call",
                        tool_calls_made=tool_calls_made,
                        iterations=iteration,
                    )
                )
            if response.tool_calls:
                for tool_call in response.tool_calls:
                    tool_calls_made += 1
                    if tool_calls_made > self.max_tool_calls:
                        return incomplete_to_repo_result(
                            IncompleteAgentRun(
                                repo_name=repo.name,
                                reason="maximum tool call limit reached",
                                stage="tool_loop",
                                tool_calls_made=tool_calls_made - 1,
                                iterations=iteration,
                            )
                        )
                    if tool_call.name not in self.tool_registry.names():
                        return incomplete_to_repo_result(
                            IncompleteAgentRun(
                                repo_name=repo.name,
                                reason=(
                                    "model requested unregistered tool: "
                                    f"{tool_call.name}"
                                ),
                                stage="tool_dispatch",
                                tool_calls_made=tool_calls_made,
                                iterations=iteration,
                            )
                        )
                    requested_repo = tool_call.arguments.get("repo_name")
                    if requested_repo != repo.name:
                        return incomplete_to_repo_result(
                            IncompleteAgentRun(
                                repo_name=repo.name,
                                reason=(
                                    "model requested tool access for a different "
                                    f"repo: {requested_repo}"
                                ),
                                stage="tool_dispatch",
                                tool_calls_made=tool_calls_made,
                                iterations=iteration,
                            )
                        )
                    try:
                        result = self.tool_registry.call(
                            tool_call.name, tool_call.arguments
                        )
                    except Exception as exc:
                        return incomplete_to_repo_result(
                            IncompleteAgentRun(
                                repo_name=repo.name,
                                reason=str(exc),
                                stage="tool_dispatch",
                                tool_calls_made=tool_calls_made,
                                iterations=iteration,
                            )
                        )
                    if (
                        tool_call.name == "run_configured_safe_command"
                        and result.ok
                        and "command_result" in result.data
                    ):
                        executed_command_results.append(
                            CommandResult.model_validate(
                                result.data["command_result"]
                            )
                        )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_call.name,
                            "content": result.model_dump_json(),
                        }
                    )
                continue
            if response.content:
                try:
                    output = RepoInspectorOutput.model_validate_json(response.content)
                except ValidationError as exc:
                    return incomplete_to_repo_result(
                        IncompleteAgentRun(
                            repo_name=repo.name,
                            reason=f"malformed structured output: {exc}",
                            stage="structured_output",
                            tool_calls_made=tool_calls_made,
                            iterations=iteration,
                        )
                    )
                mismatch = validate_repo_output_matches(repo, output)
                if mismatch is not None:
                    return incomplete_to_repo_result(
                        IncompleteAgentRun(
                            repo_name=repo.name,
                            reason=mismatch,
                            stage="structured_output",
                            tool_calls_made=tool_calls_made,
                            iterations=iteration,
                        )
                    )
                return RepoResult(
                    repo_name=repo.name,
                    path=str(repo.path) if repo.path is not None else None,
                    findings=[
                        *output.findings,
                        *command_results_findings(
                            repo.name, executed_command_results
                        ),
                    ],
                    skipped_checks=output.skipped_checks,
                    command_results=executed_command_results,
                    errors=output.errors,
                )
            messages.append(
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "instruction": (
                                "Return structured JSON or call a registered "
                                "tool."
                            ),
                            "repo_name": repo.name,
                        }
                    ),
                }
            )
        return incomplete_to_repo_result(
            IncompleteAgentRun(
                repo_name=repo.name,
                reason="maximum agent iteration limit reached",
                stage="tool_loop",
                tool_calls_made=tool_calls_made,
                iterations=self.max_iterations,
            )
        )


def checks_include(repo: RepoConfig, check: CheckName) -> bool:
    """Return whether a repo has a check configured."""

    return check in repo.checks


def command_result_findings(
    repo_name: str, command_result: CommandResult
) -> list[Finding]:
    """Convert failed command results into normalized findings."""

    category = COMMAND_LABEL_CATEGORIES.get(
        command_result.label, FindingCategory.RUNTIME
    )
    output_note = "No stdout/stderr excerpt was captured."
    if command_result.stderr_excerpt and command_result.stdout_excerpt:
        output_note = "Redacted stdout and stderr excerpts were captured."
    elif command_result.stderr_excerpt:
        output_note = "A redacted stderr excerpt was captured."
    elif command_result.stdout_excerpt:
        output_note = "A redacted stdout excerpt was captured."
    if command_result.timed_out:
        timeout_description = "the configured timeout"
        if command_result.timeout_seconds is not None:
            timeout_description = f"{command_result.timeout_seconds} seconds"
        return [
            Finding(
                repo_name=repo_name,
                severity=Severity.MEDIUM,
                category=category,
                title=f"{command_result.label} command timed out",
                description=(
                    f"The `{command_result.label}` command timed out after "
                    f"{timeout_description}. {output_note}"
                ),
                command_label=command_result.label,
                needs_human_review=True,
            )
        ]
    if command_result.exit_code not in (None, 0):
        return [
            Finding(
                repo_name=repo_name,
                severity=Severity.MEDIUM,
                category=category,
                title=f"{command_result.label} command failed",
                description=(
                    f"The `{command_result.label}` command exited with code "
                    f"{command_result.exit_code}. {output_note}"
                ),
                command_label=command_result.label,
                needs_human_review=True,
            )
        ]
    return []


def command_results_findings(
    repo_name: str, command_results: list[CommandResult]
) -> list[Finding]:
    """Convert a list of command results into normalized findings."""

    findings: list[Finding] = []
    for command_result in command_results:
        findings.extend(command_result_findings(repo_name, command_result))
    return findings


def validate_repo_output_matches(
    repo: RepoConfig, output: RepoInspectorOutput
) -> str | None:
    """Return a mismatch reason if structured output crosses repo boundaries."""

    if output.repo_name != repo.name:
        return f"structured output used unexpected repo_name: {output.repo_name}"
    for finding in output.findings:
        if finding.repo_name != repo.name:
            return f"finding used unexpected repo_name: {finding.repo_name}"
    for skipped in output.skipped_checks:
        if skipped.repo_name != repo.name:
            return f"skipped check used unexpected repo_name: {skipped.repo_name}"
    for error in output.errors:
        if error.repo_name is not None and error.repo_name != repo.name:
            return f"agent error used unexpected repo_name: {error.repo_name}"
    return None
