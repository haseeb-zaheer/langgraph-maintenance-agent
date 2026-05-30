from __future__ import annotations

from langgraph_maintenance_agent.schemas import (
    AgentError,
    CommandResult,
    DeliveryStatus,
    Finding,
    FindingCategory,
    RepoInspectionMetadata,
    RepoResult,
    Severity,
    SkippedCheck,
    SourceFileMetadata,
    SourceReviewCoverage,
    SourceReviewPlan,
    SourceReviewTarget,
    SummaryOutput,
    ToolCallSummary,
)


def make_finding(**overrides: object) -> Finding:
    data = {
        "repo_name": "example",
        "severity": Severity.MEDIUM,
        "category": FindingCategory.DOCS,
        "title": "Missing architecture doc",
        "description": "The repository does not include ARCHITECTURE.md.",
        "evidence_paths": ["README.md"],
        "suggested_action": "Add an architecture overview.",
    }
    data.update(overrides)
    return Finding.model_validate(data)


def test_finding_serialization_round_trip() -> None:
    finding = make_finding()

    serialized = finding.model_dump(mode="json")
    restored = Finding.model_validate(serialized)

    assert restored == finding
    assert restored.id is not None


def test_fingerprint_is_stable_for_equivalent_findings() -> None:
    first = make_finding(evidence_paths=["README.md", "AGENTS.md"])
    second = make_finding(evidence_paths=["AGENTS.md", "README.md"])

    assert first.id == second.id


def test_fingerprint_differs_for_different_findings() -> None:
    first = make_finding(title="Missing architecture doc")
    second = make_finding(title="Dirty worktree")

    assert first.id != second.id


def test_command_result_serialization() -> None:
    result = CommandResult(
        label="tests",
        command=["pytest"],
        working_directory="/path/to/example",
        exit_code=0,
        stdout_excerpt="ok",
    )

    assert CommandResult.model_validate(result.model_dump(mode="json")) == result


def test_repo_result_groups_structured_data() -> None:
    finding = make_finding()
    skipped = SkippedCheck(
        repo_name="example",
        check_name="tests",
        reason="No safe command configured.",
    )
    error = AgentError(message="partial failure", repo_name="example")

    result = RepoResult(
        repo_name="example",
        path="/path/to/example",
        findings=[finding],
        skipped_checks=[skipped],
        errors=[error],
    )

    assert result.findings == [finding]
    assert result.skipped_checks == [skipped]
    assert result.errors == [error]


def test_repo_result_metadata_serialization() -> None:
    metadata = RepoInspectionMetadata(
        tool_calls=[
            ToolCallSummary(
                tool_name="git_status",
                status="completed",
                argument_keys=["repo_name"],
            )
        ],
        tool_calls_made=1,
        iterations=1,
        model_provider="none",
    )
    result = RepoResult(repo_name="example", metadata=metadata)

    restored = RepoResult.model_validate(result.model_dump(mode="json"))

    assert restored.metadata.tool_calls_made == 1
    assert restored.metadata.tool_calls[0].tool_name == "git_status"


def test_source_review_plan_serialization() -> None:
    plan = SourceReviewPlan(
        repo_name="example",
        rationale="Review API and config glue.",
        targets=[
            SourceReviewTarget(
                path="src/app/api/chat/route.ts",
                reason="API route with request handling.",
            )
        ],
    )

    assert SourceReviewPlan.model_validate(plan.model_dump(mode="json")) == plan


def test_source_review_coverage_serialization() -> None:
    coverage = SourceReviewCoverage(
        candidate_files=2,
        planned_files=1,
        read_files=1,
        bytes_read=512,
        skipped_files=0,
        generated_files_skipped=3,
        review_mode="llm-planned",
        plan_rationale="Review high-risk route.",
        candidates=[
            SourceFileMetadata(
                path="src/app/api/chat/route.ts",
                size_bytes=512,
                language="typescript",
                signals=["api-route"],
                priority=105,
                nearby_test=False,
            )
        ],
    )

    restored = SourceReviewCoverage.model_validate(coverage.model_dump(mode="json"))

    assert restored.candidate_files == 2
    assert restored.candidates[0].signals == ["api-route"]


def test_delivery_status_serialization() -> None:
    status = DeliveryStatus(
        destination="discord",
        attempted=True,
        success=False,
        message="missing webhook",
    )

    assert DeliveryStatus.model_validate(status.model_dump(mode="json")) == status


def test_summary_output_serialization() -> None:
    summary = SummaryOutput(
        executive_summary="Two repositories inspected.",
        next_actions=["Review findings."],
    )

    assert SummaryOutput.model_validate(summary.model_dump(mode="json")) == summary
