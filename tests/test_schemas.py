from __future__ import annotations

from langgraph_maintenance_agent.schemas import (
    AgentError,
    CommandResult,
    DeliveryStatus,
    Finding,
    FindingCategory,
    RepoResult,
    Severity,
    SkippedCheck,
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


def test_delivery_status_serialization() -> None:
    status = DeliveryStatus(
        destination="discord",
        attempted=True,
        success=False,
        message="missing webhook",
    )

    assert DeliveryStatus.model_validate(status.model_dump(mode="json")) == status
