"""Sequential tool-using repository inspector agent."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from langgraph_maintenance_agent.agents.prompts import (
    REPO_INSPECTOR_SYSTEM_PROMPT,
    SOURCE_REVIEW_FINDINGS_SYSTEM_PROMPT,
    SOURCE_REVIEW_PLANNER_SYSTEM_PROMPT,
    repo_inspector_user_prompt,
    source_review_findings_user_prompt,
    source_review_planner_user_prompt,
    source_review_repair_user_prompt,
)
from langgraph_maintenance_agent.config import (
    COMMAND_CHECK_LABELS,
    CheckName,
    RepoConfig,
    allowed_command_labels,
)
from langgraph_maintenance_agent.llm.openrouter import OpenRouterClient
from langgraph_maintenance_agent.reporting.redaction import redact_text
from langgraph_maintenance_agent.runtime.text import bound_text
from langgraph_maintenance_agent.schemas import (
    AgentError,
    CommandResult,
    Finding,
    FindingCategory,
    IncompleteAgentRun,
    RepoInspectionMetadata,
    RepoInspectorOutput,
    RepoResult,
    Severity,
    SkippedCheck,
    SourceFileMetadata,
    SourceReviewCoverage,
    SourceReviewFinding,
    SourceReviewOutput,
    SourceReviewPlan,
    ToolCallSummary,
)
from langgraph_maintenance_agent.tools.registry import ToolRegistry
from langgraph_maintenance_agent.tools.results import ToolCallRecord, ToolResult

COMMAND_LABEL_CATEGORIES: dict[str, FindingCategory] = {
    "tests": FindingCategory.TEST,
    "lint": FindingCategory.STATIC,
    "build": FindingCategory.BUILD,
    "python-syntax": FindingCategory.TEST,
}

CHECK_EVIDENCE_TOOLS: dict[CheckName, set[str]] = {
    CheckName.GIT_STATUS: {"git_status", "latest_commit"},
    CheckName.DOCS: {"list_files"},
    CheckName.STATIC_SEARCH: {"search_static_markers"},
    CheckName.DEPENDENCY_METADATA: {"detect_dependency_manifests"},
    CheckName.TESTS: {"run_configured_safe_command"},
    CheckName.LINT: {"run_configured_safe_command"},
    CheckName.BUILD: {"run_configured_safe_command"},
    CheckName.PYTHON_SYNTAX: {"run_configured_safe_command"},
    CheckName.SOURCE_REVIEW: {
        "summarize_source_tree",
        "list_source_files",
        "read_source_files",
    },
    CheckName.BUG_RISK_REVIEW: {
        "summarize_source_tree",
        "list_source_files",
        "read_source_files",
    },
    CheckName.REFACTOR_REVIEW: {
        "summarize_source_tree",
        "list_source_files",
        "read_source_files",
    },
    CheckName.TEST_GAP_REVIEW: {
        "summarize_source_tree",
        "list_source_files",
        "read_source_files",
    },
}

SOURCE_REVIEW_CHECKS = {
    CheckName.SOURCE_REVIEW,
    CheckName.BUG_RISK_REVIEW,
    CheckName.REFACTOR_REVIEW,
    CheckName.TEST_GAP_REVIEW,
}
SOURCE_REVIEW_CATEGORIES = {
    FindingCategory.BUG_RISK,
    FindingCategory.REFACTOR,
    FindingCategory.CODE_QUALITY,
    FindingCategory.TEST_GAP,
}


def incomplete_to_repo_result(
    incomplete: IncompleteAgentRun,
    metadata: RepoInspectionMetadata | None = None,
) -> RepoResult:
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
        metadata=metadata
        or RepoInspectionMetadata(
            tool_calls_made=incomplete.tool_calls_made,
            iterations=incomplete.iterations,
        ),
    )


def summarize_tool_call(record: ToolCallRecord) -> ToolCallSummary:
    """Return public-safe metadata for one bounded tool call."""

    error_code = None
    if record.result is not None and record.result.error is not None:
        error_code = record.result.error.code
    return ToolCallSummary(
        tool_name=record.tool_name,
        status=record.status,
        argument_keys=sorted(record.arguments),
        error_code=error_code or record.error,
    )


class RepoInspectorAgent:
    """Tool-using repo inspector with deterministic fallback."""

    def __init__(
        self,
        *,
        tool_registry: ToolRegistry,
        llm_client: OpenRouterClient | None = None,
        max_tool_calls: int = 80,
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
        if repo_has_source_review(repo):
            results.extend(
                [
                    call("summarize_source_tree", {"repo_name": repo.name}),
                    call("list_source_files", {"repo_name": repo.name}),
                ]
            )
        findings: list[Finding] = []
        skipped = [
            SkippedCheck(
                repo_name=repo.name,
                check_name="llm-inspection",
                reason="No-LLM mode used deterministic safe tool fallback.",
            )
        ]
        if repo_has_source_review(repo):
            skipped.append(
                SkippedCheck(
                    repo_name=repo.name,
                    check_name="source-review",
                    reason=(
                        "Semantic source-code review requires LLM mode; no-LLM "
                        "mode only collected bounded source metadata."
                    ),
                )
            )
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
            metadata=RepoInspectionMetadata(
                tool_calls=[summarize_tool_call(record) for record in tool_calls],
                tool_calls_made=len(tool_calls),
                iterations=1,
                model_provider="none",
            ),
        )

    def inspect_with_llm(self, repo: RepoConfig) -> RepoResult:
        """Run the OpenRouter-backed tool loop."""

        assert self.llm_client is not None
        if repo_has_source_review(repo):
            return self.inspect_source_review_with_llm(repo)
        return self.inspect_tool_loop_with_llm(repo)

    def inspect_source_review_with_llm(self, repo: RepoConfig) -> RepoResult:
        """Run deterministic staged source review: map, plan, read, find."""

        assert self.llm_client is not None
        records: list[ToolCallRecord] = []

        def call(name: str, args: dict[str, Any]) -> ToolResult:
            result = self.tool_registry.call(name, args)
            records.append(
                ToolCallRecord(
                    tool_name=name,
                    repo_name=repo.name,
                    arguments=args,
                    status="completed" if result.ok else "failed",
                    result=result,
                )
            )
            return result

        summary_result = call("summarize_source_tree", {"repo_name": repo.name})
        list_result = call("list_source_files", {"repo_name": repo.name})
        if not summary_result.ok or not list_result.ok:
            return incomplete_to_repo_result(
                IncompleteAgentRun(
                    repo_name=repo.name,
                    reason="source metadata tools did not complete",
                    stage="source_review_metadata",
                    tool_calls_made=len(records),
                    iterations=1,
                ),
                metadata=RepoInspectionMetadata(
                    tool_calls=[summarize_tool_call(record) for record in records],
                    tool_calls_made=len(records),
                    iterations=1,
                    model_provider="openrouter",
                    model_name=getattr(self.llm_client, "model", None),
                    source_review=SourceReviewCoverage(review_mode="incomplete"),
                ),
            )
        candidates = _source_candidates_from_tool_result(list_result)
        coverage = SourceReviewCoverage(
            candidate_files=int(list_result.data.get("total_matching_files", 0)),
            generated_files_skipped=int(
                list_result.data.get("generated_files_skipped", 0)
            ),
            review_mode="llm-planned",
            candidates=candidates,
        )
        try:
            plan_response = self.llm_client.chat(
                messages=[
                    {"role": "system", "content": SOURCE_REVIEW_PLANNER_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": source_review_planner_user_prompt(
                            repo_name=repo.name,
                            max_plan_files=repo.source_review_max_plan_files,
                            source_metadata=json.dumps(
                                {
                                    "source_tree": summary_result.data,
                                    "source_files": list_result.data,
                                },
                                sort_keys=True,
                            ),
                        ),
                    },
                ],
                response_schema=SourceReviewPlan.model_json_schema(),
            )
            plan = SourceReviewPlan.model_validate_json(plan_response.content or "")
        except Exception as exc:
            return _source_review_incomplete_result(
                repo=repo,
                records=records,
                coverage=coverage,
                reason=f"malformed or missing source-review plan: {exc}",
                stage="source_review_plan",
                model_name=getattr(self.llm_client, "model", None),
            )
        plan_error = validate_source_review_plan(
            repo=repo,
            plan=plan,
            approved_candidates={candidate.path for candidate in candidates},
        )
        if plan_error is not None:
            return _source_review_incomplete_result(
                repo=repo,
                records=records,
                coverage=coverage.model_copy(
                    update={
                        "planned_files": len(plan.targets),
                        "plan_rationale": plan.rationale,
                        "planned": plan.targets,
                    }
                ),
                reason=plan_error,
                stage="source_review_plan",
                model_name=getattr(self.llm_client, "model", None),
            )
        planned_paths = [target.path for target in plan.targets]
        read_result = call(
            "read_source_files",
            {"repo_name": repo.name, "relative_paths": planned_paths},
        )
        if not read_result.ok:
            message = read_result.error.message if read_result.error else "read failed"
            return _source_review_incomplete_result(
                repo=repo,
                records=records,
                coverage=coverage,
                reason=message,
                stage="source_review_read",
                model_name=getattr(self.llm_client, "model", None),
            )
        coverage = SourceReviewCoverage.model_validate(
            {
                **coverage.model_dump(mode="json"),
                "planned_files": len(plan.targets),
                "read_files": len(read_result.data.get("read", [])),
                "bytes_read": int(read_result.data.get("bytes_read", 0)),
                "skipped_files": len(read_result.data.get("skipped", [])),
                "plan_rationale": plan.rationale,
                "planned": plan.targets,
                "read": read_result.data.get("read", []),
                "skipped": read_result.data.get("skipped", []),
            }
        )
        read_paths = {item["path"] for item in read_result.data.get("read", [])}
        if not read_paths:
            return _source_review_incomplete_result(
                repo=repo,
                records=records,
                coverage=coverage,
                reason="source-review plan produced no readable files",
                stage="source_review_read",
                model_name=getattr(self.llm_client, "model", None),
            )
        metadata_paths = set(read_paths) | {candidate.path for candidate in candidates}
        source_output_result = _request_source_review_output(
            client=self.llm_client,
            repo=repo,
            plan=plan,
            coverage=coverage,
            source_tree_data=summary_result.data,
            read_file_data=read_result.data.get("files", []),
            read_paths=read_paths,
            metadata_paths=metadata_paths,
        )
        output, coverage, output_error = source_output_result
        if output_error is not None:
            return _source_review_incomplete_result(
                repo=repo,
                records=records,
                coverage=coverage,
                reason=output_error,
                stage="source_review_findings_repair"
                if coverage.repair_attempted
                else "source_review_findings",
                model_name=getattr(self.llm_client, "model", None),
            )
        assert output is not None
        return RepoResult(
            repo_name=repo.name,
            path=str(repo.path) if repo.path is not None else None,
            findings=[finding.to_finding() for finding in output.findings],
            skipped_checks=output.skipped_checks,
            errors=output.errors,
            metadata=RepoInspectionMetadata(
                tool_calls=[summarize_tool_call(record) for record in records],
                tool_calls_made=len(records),
                iterations=2,
                model_provider="openrouter",
                model_name=getattr(self.llm_client, "model", None),
                source_review=coverage,
            ),
        )

    def inspect_tool_loop_with_llm(self, repo: RepoConfig) -> RepoResult:
        """Run the OpenRouter-backed generic tool loop."""

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
        completed_evidence_tools: set[str] = set()
        tool_call_records: list[ToolCallRecord] = []
        tool_calls_made = 0
        for iteration in range(1, self.max_iterations + 1):
            missing_tools = missing_required_evidence_tools(
                repo, completed_evidence_tools
            )
            try:
                response = self.llm_client.chat(
                    messages=messages,
                    tools=self.tool_registry.schemas(),
                    response_schema=RepoInspectorOutput.model_json_schema(),
                    tool_choice="required" if missing_tools else "auto",
                )
            except Exception as exc:
                return incomplete_to_repo_result(
                    IncompleteAgentRun(
                        repo_name=repo.name,
                        reason=str(exc),
                        stage="model_call",
                        tool_calls_made=tool_calls_made,
                        iterations=iteration,
                    ),
                    metadata=RepoInspectionMetadata(
                        tool_calls=[
                            summarize_tool_call(record)
                            for record in tool_call_records
                        ],
                        tool_calls_made=tool_calls_made,
                        iterations=iteration,
                        model_provider="openrouter",
                    ),
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
                            ),
                            metadata=RepoInspectionMetadata(
                                tool_calls=[
                                    summarize_tool_call(record)
                                    for record in tool_call_records
                                ],
                                tool_calls_made=tool_calls_made - 1,
                                iterations=iteration,
                                model_provider="openrouter",
                            ),
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
                            ),
                            metadata=RepoInspectionMetadata(
                                tool_calls=[
                                    summarize_tool_call(record)
                                    for record in tool_call_records
                                ],
                                tool_calls_made=tool_calls_made,
                                iterations=iteration,
                                model_provider="openrouter",
                            ),
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
                            ),
                            metadata=RepoInspectionMetadata(
                                tool_calls=[
                                    summarize_tool_call(record)
                                    for record in tool_call_records
                                ],
                                tool_calls_made=tool_calls_made,
                                iterations=iteration,
                                model_provider="openrouter",
                            ),
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
                            ),
                            metadata=RepoInspectionMetadata(
                                tool_calls=[
                                    summarize_tool_call(record)
                                    for record in tool_call_records
                                ],
                                tool_calls_made=tool_calls_made,
                                iterations=iteration,
                                model_provider="openrouter",
                            ),
                        )
                    tool_call_records.append(
                        ToolCallRecord(
                            tool_name=tool_call.name,
                            repo_name=repo.name,
                            arguments=tool_call.arguments,
                            status="completed" if result.ok else "failed",
                            result=result,
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
                    if result.ok:
                        completed_evidence_tools.add(tool_call.name)
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
                        ),
                        metadata=RepoInspectionMetadata(
                            tool_calls=[
                                summarize_tool_call(record)
                                for record in tool_call_records
                            ],
                            tool_calls_made=tool_calls_made,
                            iterations=iteration,
                            model_provider="openrouter",
                        ),
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
                        ),
                        metadata=RepoInspectionMetadata(
                            tool_calls=[
                                summarize_tool_call(record)
                                for record in tool_call_records
                            ],
                            tool_calls_made=tool_calls_made,
                            iterations=iteration,
                            model_provider="openrouter",
                        ),
                    )
                source_review_error = validate_source_review_findings(output.findings)
                if source_review_error is not None:
                    return incomplete_to_repo_result(
                        IncompleteAgentRun(
                            repo_name=repo.name,
                            reason=source_review_error,
                            stage="structured_output",
                            tool_calls_made=tool_calls_made,
                            iterations=iteration,
                        ),
                        metadata=RepoInspectionMetadata(
                            tool_calls=[
                                summarize_tool_call(record)
                                for record in tool_call_records
                            ],
                            tool_calls_made=tool_calls_made,
                            iterations=iteration,
                            model_provider="openrouter",
                        ),
                    )
                if missing_tools:
                    messages.append(
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "instruction": (
                                        "Do not return final structured JSON yet. "
                                        "Call the registered tools required for "
                                        "the configured checks first."
                                    ),
                                    "repo_name": repo.name,
                                    "required_tools": sorted(missing_tools),
                                }
                            ),
                        }
                    )
                    continue
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
                    metadata=RepoInspectionMetadata(
                        tool_calls=[
                            summarize_tool_call(record) for record in tool_call_records
                        ],
                        tool_calls_made=tool_calls_made,
                        iterations=iteration,
                        model_provider="openrouter",
                    ),
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
            ),
            metadata=RepoInspectionMetadata(
                tool_calls=[
                    summarize_tool_call(record) for record in tool_call_records
                ],
                tool_calls_made=tool_calls_made,
                iterations=self.max_iterations,
                model_provider="openrouter",
            ),
        )


def checks_include(repo: RepoConfig, check: CheckName) -> bool:
    """Return whether a repo has a check configured."""

    return check in repo.checks


def required_evidence_tools(repo: RepoConfig) -> set[str]:
    """Return safe tools that must run before LLM final output is accepted."""

    tools: set[str] = set()
    for check in repo.checks:
        tools.update(CHECK_EVIDENCE_TOOLS.get(check, set()))
    if any(check in COMMAND_CHECK_LABELS for check in repo.checks):
        tools.add("run_configured_safe_command")
    return tools


def repo_has_source_review(repo: RepoConfig) -> bool:
    """Return whether a repo has semantic source review checks configured."""

    return bool(set(repo.checks) & SOURCE_REVIEW_CHECKS)


def missing_required_evidence_tools(
    repo: RepoConfig, completed_tools: set[str]
) -> set[str]:
    """Return required evidence tools not yet completed successfully."""

    return required_evidence_tools(repo) - completed_tools


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


def validate_source_review_output_matches(
    repo: RepoConfig, output: SourceReviewOutput
) -> str | None:
    """Return a mismatch reason if source-review output crosses repo boundaries."""

    if output.repo_name != repo.name:
        return f"source-review output used unexpected repo_name: {output.repo_name}"
    for finding in output.findings:
        if finding.repo_name != repo.name:
            return (
                "source-review finding used unexpected repo_name: "
                f"{finding.repo_name}"
            )
    for skipped in output.skipped_checks:
        if skipped.repo_name != repo.name:
            return f"skipped check used unexpected repo_name: {skipped.repo_name}"
    for error in output.errors:
        if error.repo_name is not None and error.repo_name != repo.name:
            return f"agent error used unexpected repo_name: {error.repo_name}"
    return None


def validate_source_review_plan(
    *,
    repo: RepoConfig,
    plan: SourceReviewPlan,
    approved_candidates: set[str],
) -> str | None:
    """Return a validation error if a staged source-review plan is unsafe."""

    if plan.repo_name != repo.name:
        return f"source-review plan used unexpected repo_name: {plan.repo_name}"
    if not plan.targets:
        return "source-review plan did not include any target files"
    if len(plan.targets) > repo.source_review_max_plan_files:
        return "source-review plan exceeded source_review_max_plan_files"
    seen: set[str] = set()
    for target in plan.targets:
        if target.path not in approved_candidates:
            return f"source-review plan selected unapproved path: {target.path}"
        if target.path in seen:
            return f"source-review plan duplicated path: {target.path}"
        if not target.reason.strip():
            return f"source-review plan target lacks reason: {target.path}"
        seen.add(target.path)
    return None


def validate_source_review_findings(
    findings: list[Finding] | list[SourceReviewFinding],
    *,
    read_paths: set[str] | None = None,
    metadata_paths: set[str] | None = None,
) -> str | None:
    """Return a validation error if source-review findings lack read evidence."""

    for finding in findings:
        if finding.category not in SOURCE_REVIEW_CATEGORIES:
            continue
        if not finding.evidence_paths:
            return f"source-review finding lacks evidence paths: {finding.title}"
        if not finding.suggested_action:
            return f"source-review finding lacks suggested action: {finding.title}"
        if read_paths is None:
            continue
        allowed_paths = read_paths
        if finding.category == FindingCategory.TEST_GAP:
            allowed_paths = metadata_paths or read_paths
        for path in finding.evidence_paths:
            if path not in allowed_paths:
                return (
                    "source-review finding cites unread or unapproved evidence "
                    f"path: {path}"
                )
    return None


def _request_source_review_output(
    *,
    client: OpenRouterClient,
    repo: RepoConfig,
    plan: SourceReviewPlan,
    coverage: SourceReviewCoverage,
    source_tree_data: dict[str, Any],
    read_file_data: list[Any],
    read_paths: set[str],
    metadata_paths: set[str],
) -> tuple[SourceReviewOutput | None, SourceReviewCoverage, str | None]:
    """Request source-review findings and make one validation repair attempt."""

    prompt_payload = json.dumps(
        {
            "plan": plan.model_dump(mode="json"),
            "coverage": coverage.model_dump(mode="json"),
            "source_tree_metadata": source_tree_data,
            "read_files": read_file_data,
            "allowed_read_evidence_paths": sorted(read_paths),
            "allowed_metadata_paths_for_test_gap": sorted(metadata_paths),
        },
        sort_keys=True,
    )
    messages = [
        {
            "role": "system",
            "content": SOURCE_REVIEW_FINDINGS_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": source_review_findings_user_prompt(
                repo_name=repo.name,
                plan_and_evidence=prompt_payload,
            ),
        },
    ]
    response_content: str | None = None
    try:
        response = client.chat(
            messages=messages,
            response_schema=SourceReviewOutput.model_json_schema(),
        )
        response_content = response.content
        output = SourceReviewOutput.model_validate_json(response.content or "")
        validation_error = _validate_source_review_output(
            repo=repo,
            output=output,
            read_paths=read_paths,
            metadata_paths=metadata_paths,
        )
        if validation_error is None:
            return (
                output,
                _coverage_with_validation(coverage, status="accepted"),
                None,
            )
    except Exception as exc:
        validation_error = f"malformed source-review findings output: {exc}"

    repair_messages = [
        {
            "role": "system",
            "content": SOURCE_REVIEW_FINDINGS_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": source_review_repair_user_prompt(
                repo_name=repo.name,
                validation_error=validation_error,
                allowed_read_paths=sorted(read_paths),
                allowed_metadata_paths=sorted(metadata_paths),
                original_output=_redacted_model_output(response_content),
            ),
        },
    ]
    try:
        repair_response = client.chat(
            messages=repair_messages,
            response_schema=SourceReviewOutput.model_json_schema(),
        )
        repaired = SourceReviewOutput.model_validate_json(
            repair_response.content or ""
        )
        repair_error = _validate_source_review_output(
            repo=repo,
            output=repaired,
            read_paths=read_paths,
            metadata_paths=metadata_paths,
        )
        if repair_error is None:
            return (
                repaired,
                _coverage_with_validation(
                    coverage,
                    status="repaired",
                    repair_attempted=True,
                ),
                None,
            )
    except Exception as exc:
        repair_error = f"malformed repaired source-review output: {exc}"

    rejected_coverage = _coverage_with_validation(
        coverage,
        status="rejected",
        validation_error=repair_error,
        repair_attempted=True,
    )
    return None, rejected_coverage, repair_error


def _validate_source_review_output(
    *,
    repo: RepoConfig,
    output: SourceReviewOutput,
    read_paths: set[str],
    metadata_paths: set[str],
) -> str | None:
    mismatch = validate_source_review_output_matches(repo, output)
    if mismatch is not None:
        return mismatch
    return validate_source_review_findings(
        output.findings,
        read_paths=read_paths,
        metadata_paths=metadata_paths,
    )


def _coverage_with_validation(
    coverage: SourceReviewCoverage,
    *,
    status: str,
    validation_error: str | None = None,
    repair_attempted: bool = False,
) -> SourceReviewCoverage:
    return coverage.model_copy(
        update={
            "validation_status": status,
            "validation_error": redact_text(validation_error)
            if validation_error
            else None,
            "repair_attempted": repair_attempted,
        }
    )


def _redacted_model_output(content: str | None) -> str:
    if not content:
        return "none"
    return bound_text(redact_text(content), 4_000)


def _source_candidates_from_tool_result(result: ToolResult) -> list[SourceFileMetadata]:
    raw_candidates = result.data.get("ranked_candidates") or result.data.get(
        "files", []
    )
    candidates: list[SourceFileMetadata] = []
    for item in raw_candidates:
        if "language" in item:
            candidates.append(SourceFileMetadata.model_validate(item))
        else:
            path = str(item["path"])
            candidates.append(
                SourceFileMetadata(
                    path=path,
                    size_bytes=int(item.get("size_bytes") or 0),
                    language="unknown",
                )
            )
    return candidates


def _source_review_incomplete_result(
    *,
    repo: RepoConfig,
    records: list[ToolCallRecord],
    coverage: SourceReviewCoverage,
    reason: str,
    stage: str,
    model_name: str | None,
) -> RepoResult:
    return incomplete_to_repo_result(
        IncompleteAgentRun(
            repo_name=repo.name,
            reason=reason,
            stage=stage,
            tool_calls_made=len(records),
            iterations=1,
        ),
        metadata=RepoInspectionMetadata(
            tool_calls=[summarize_tool_call(record) for record in records],
            tool_calls_made=len(records),
            iterations=1,
            model_provider="openrouter",
            model_name=model_name,
            source_review=coverage.model_copy(update={"review_mode": "incomplete"}),
        ),
    )
