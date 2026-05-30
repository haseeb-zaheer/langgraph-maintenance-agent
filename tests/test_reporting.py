from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from langgraph_maintenance_agent.config import AppConfig, ConfigError, RepoConfig
from langgraph_maintenance_agent.graph import (
    redact_report_node,
    redact_structured_state_node,
    render_markdown_node,
    run_workflow,
    summarize_with_agent_node,
)
from langgraph_maintenance_agent.reporting.discord import (
    DiscordDeliveryError,
    chunk_discord_content,
    send_discord_content,
)
from langgraph_maintenance_agent.reporting.markdown import REPORT_HEADINGS
from langgraph_maintenance_agent.reporting.redaction import (
    REDACTION_MARKER,
    redact_text,
    redact_text_with_metadata,
)
from langgraph_maintenance_agent.schemas import (
    CommandResult,
    Finding,
    FindingCategory,
    ReadSourceFileMetadata,
    RepoInspectionMetadata,
    RepoResult,
    Severity,
    SourceReviewCoverage,
    SourceReviewTarget,
)
from langgraph_maintenance_agent.state import AgentState


def test_redaction_metadata_counts_secret_types() -> None:
    text = "\n".join(
        [
            "https://discord.com/api/" + "webhooks/123/token",
            "Authorization: " + "Bearer secret-token",
            "OPENROUTER_API_KEY=" + "sk-or-abcdefghijklmnop",
            "password=hunter2",
            "-----BEGIN " + "PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----",
        ]
    )

    result = redact_text_with_metadata(text)

    assert result.total_count >= 5
    assert result.counts_by_type["discord_webhook_url"] == 1
    assert result.counts_by_type["authorization_header"] == 1
    assert result.counts_by_type["private_key"] == 1
    assert "hunter2" not in result.text
    assert "secret-token" not in result.text


def test_redact_text_compatibility_helper() -> None:
    assert redact_text("token=abc") == REDACTION_MARKER


def test_rendered_report_has_required_headings_and_empty_sections(
    tmp_path: Path,
) -> None:
    state: AgentState = {
        "config": AppConfig(
            repos=[RepoConfig(name="demo", path=tmp_path, enabled=True)]
        ),
        "selected_repos": [RepoConfig(name="demo", path=tmp_path, enabled=True)],
        "repo_results": [RepoResult(repo_name="demo", path=str(tmp_path))],
        "findings": [],
        "skipped_checks": [],
        "errors": [],
        "summary": "No issues found.",
        "next_actions": [],
        "run_id": "test",
        "started_at": "2026-05-30T00:00:00+00:00",
        "dry_run": True,
    }

    report = render_markdown_node(state)["report_markdown"] or ""

    for heading in REPORT_HEADINGS:
        assert f"## {heading}" in report
    assert "None found." in report


def test_findings_group_by_severity(tmp_path: Path) -> None:
    findings = [
        Finding(
            repo_name="demo",
            severity=Severity.CRITICAL,
            category=FindingCategory.SECURITY,
            title="Critical item",
            description="Critical description",
        ),
        Finding(
            repo_name="demo",
            severity=Severity.MEDIUM,
            category=FindingCategory.TEST,
            title="Medium item",
            description="Medium description",
        ),
    ]
    state: AgentState = {
        "selected_repos": [RepoConfig(name="demo", path=tmp_path, enabled=True)],
        "repo_results": [
            RepoResult(repo_name="demo", path=str(tmp_path), findings=findings)
        ],
        "findings": findings,
        "skipped_checks": [],
        "errors": [],
        "summary": "Summary",
        "next_actions": [],
        "run_id": "test",
        "started_at": "2026-05-30T00:00:00+00:00",
        "dry_run": True,
    }

    report = render_markdown_node(state)["report_markdown"] or ""

    assert "## Critical Findings\n\n### `demo` Critical item" in report
    assert "## Medium Priority\n\n### `demo` Medium item" in report


def test_source_review_findings_render_in_dedicated_sections(tmp_path: Path) -> None:
    findings = [
        Finding(
            repo_name="demo",
            severity=Severity.MEDIUM,
            category=FindingCategory.BUG_RISK,
            title="Possible missing validation",
            description="Input is used without validation.",
            evidence_paths=["src/app.py"],
            suggested_action="Validate the input before use.",
        ),
        Finding(
            repo_name="demo",
            severity=Severity.LOW,
            category=FindingCategory.REFACTOR,
            title="Extract repeated helper",
            description="Two branches repeat the same transformation.",
            evidence_paths=["src/app.py"],
            suggested_action="Extract the shared transformation.",
        ),
    ]
    state: AgentState = {
        "selected_repos": [RepoConfig(name="demo", path=tmp_path, enabled=True)],
        "repo_results": [
            RepoResult(repo_name="demo", path=str(tmp_path), findings=findings)
        ],
        "findings": findings,
        "skipped_checks": [],
        "errors": [],
        "summary": "Summary",
        "next_actions": [],
        "run_id": "test",
        "started_at": "2026-05-30T00:00:00+00:00",
        "dry_run": True,
    }

    report = render_markdown_node(state)["report_markdown"] or ""

    assert "## Bug Risk Review\n\n### `demo` Possible missing validation" in report
    assert "## Refactor Opportunities\n\n### `demo` Extract repeated helper" in report


def test_source_review_coverage_renders_without_source_content(tmp_path: Path) -> None:
    coverage = SourceReviewCoverage(
        candidate_files=4,
        planned_files=1,
        read_files=1,
        bytes_read=128,
        skipped_files=0,
        generated_files_skipped=2,
        review_mode="llm-planned",
        validation_status="repaired",
        repair_attempted=True,
        plan_rationale="Review API route first.",
        planned=[
            SourceReviewTarget(
                path="src/app/api/chat/route.ts",
                reason="Request handler.",
            )
        ],
        read=[
            ReadSourceFileMetadata(
                path="src/app/api/chat/route.ts",
                size_bytes=128,
                bytes_read=128,
            )
        ],
    )
    state: AgentState = {
        "selected_repos": [RepoConfig(name="demo", path=tmp_path, enabled=True)],
        "repo_results": [
            RepoResult(
                repo_name="demo",
                path=str(tmp_path),
                metadata=RepoInspectionMetadata(source_review=coverage),
            )
        ],
        "findings": [],
        "skipped_checks": [],
        "errors": [],
        "summary": "Summary",
        "next_actions": [],
        "run_id": "test",
        "started_at": "2026-05-30T00:00:00+00:00",
        "dry_run": True,
    }

    report = render_markdown_node(state)["report_markdown"] or ""

    assert "## Source Review Coverage" in report
    assert "- Candidate files: 4" in report
    assert "- Validation status: `repaired`" in report
    assert "- Repair attempted: `True`" in report
    assert "`src/app/api/chat/route.ts`" in report
    assert "export async function" not in report


def test_source_review_rejected_validation_metadata_renders(
    tmp_path: Path,
) -> None:
    coverage = SourceReviewCoverage(
        candidate_files=1,
        planned_files=1,
        read_files=1,
        bytes_read=64,
        review_mode="incomplete",
        validation_status="rejected",
        validation_error=(
            "source-review finding cites unread or unapproved evidence path"
        ),
        repair_attempted=True,
    )
    state: AgentState = {
        "selected_repos": [RepoConfig(name="demo", path=tmp_path, enabled=True)],
        "repo_results": [
            RepoResult(
                repo_name="demo",
                metadata=RepoInspectionMetadata(source_review=coverage),
            )
        ],
        "findings": [],
        "skipped_checks": [],
        "errors": [],
        "summary": "Summary",
        "next_actions": [],
        "run_id": "test",
        "started_at": "2026-05-30T00:00:00+00:00",
        "dry_run": True,
    }

    report = render_markdown_node(state)["report_markdown"] or ""

    assert "- Validation status: `rejected`" in report
    assert "unread or unapproved" in report


def test_command_result_rendering_is_redacted(tmp_path: Path) -> None:
    secret = "Authorization: " + "Bearer secret-token"
    command = CommandResult(
        label="tests",
        command=["python", "-m", "pytest"],
        working_directory=str(tmp_path),
        exit_code=1,
        stdout_excerpt=secret,
    )
    state: AgentState = {
        "selected_repos": [RepoConfig(name="demo", path=tmp_path, enabled=True)],
        "repo_results": [
            RepoResult(
                repo_name="demo",
                path=str(tmp_path),
                command_results=[command],
            )
        ],
        "findings": [],
        "skipped_checks": [],
        "errors": [],
        "summary": "Summary",
        "next_actions": [],
        "run_id": "test",
        "started_at": "2026-05-30T00:00:00+00:00",
        "dry_run": True,
        "redaction_count": 0,
        "redaction_counts_by_type": {},
    }

    rendered = render_markdown_node(state)
    report = redact_report_node(rendered)["report_markdown"] or ""

    assert "secret-token" not in report
    assert REDACTION_MARKER in report


def test_structured_redaction_preserves_schema_with_secret_lines(
    tmp_path: Path,
) -> None:
    secret = "password=hunter2"
    state: AgentState = {
        "repo_results": [],
        "findings": [
            Finding(
                repo_name="demo",
                severity=Severity.HIGH,
                category=FindingCategory.SECURITY,
                title="Secret line",
                description=secret,
            )
        ],
        "skipped_checks": [],
        "errors": [],
        "redaction_count": 0,
        "redaction_counts_by_type": {},
    }

    result = redact_structured_state_node(state)

    assert result["findings"][0].description == REDACTION_MARKER
    assert result["redaction_count"] == 1


def test_final_report_redaction_adds_warning_for_summary_secret(
    tmp_path: Path,
) -> None:
    state: AgentState = {
        "selected_repos": [RepoConfig(name="demo", path=tmp_path, enabled=True)],
        "repo_results": [RepoResult(repo_name="demo", path=str(tmp_path))],
        "findings": [],
        "skipped_checks": [],
        "errors": [],
        "summary": "summary contains token=abc123",
        "next_actions": [],
        "run_id": "test",
        "started_at": "2026-05-30T00:00:00+00:00",
        "dry_run": True,
        "redaction_count": 0,
        "redaction_counts_by_type": {},
    }

    rendered = render_markdown_node(state)
    report = redact_report_node(rendered)["report_markdown"] or ""

    assert "token=abc123" not in report
    assert "Redaction warning:" in report


def test_discord_chunking_preserves_content() -> None:
    content = ("paragraph\n\n" * 250) + "end"

    chunks = chunk_discord_content(content)

    assert len(chunks) > 1
    assert all(len(chunk) <= 2000 for chunk in chunks)
    restored = "".join(chunk.split(" ", 1)[1] for chunk in chunks)
    assert restored == content
    assert chunks[0].startswith("(1/")


def test_discord_exact_boundary_is_single_chunk() -> None:
    content = "x" * 1900

    assert chunk_discord_content(content) == [content]


def test_discord_missing_webhook_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGGRAPH_MAINTENANCE_DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

    with pytest.raises(DiscordDeliveryError, match="webhook URL is not configured"):
        send_discord_content("hello")


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class FakeHttpClient:
    def __init__(self, status_code: int = 204) -> None:
        self.status_code = status_code
        self.payloads: list[dict[str, str]] = []

    def post(self, _url: str, *, json: dict[str, str]) -> FakeResponse:
        self.payloads.append(json)
        return FakeResponse(self.status_code)


def test_discord_send_redacts_webhook_payload() -> None:
    client = FakeHttpClient()
    secret = "https://discord.com/api/" + "webhooks/123/token"

    result = send_discord_content(
        secret,
        webhook_url="https://example.invalid",
        http_client=client,  # type: ignore[arg-type]
    )

    assert result.messages_sent == 1
    assert secret not in client.payloads[0]["content"]
    assert REDACTION_MARKER in client.payloads[0]["content"]


def test_discord_http_failure() -> None:
    client = FakeHttpClient(status_code=500)

    with pytest.raises(DiscordDeliveryError, match="HTTP 500"):
        send_discord_content(
            "hello",
            webhook_url="https://example.invalid",
            http_client=client,  # type: ignore[arg-type]
        )


class FakeSummaryClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.messages: list[dict[str, Any]] = []

    def chat(self, **kwargs: Any) -> Any:
        self.messages = kwargs["messages"]
        return type("Response", (), {"content": self.content})()


def test_summary_agent_success_uses_redacted_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeSummaryClient(
        '{"executive_summary":"Clean summary","next_actions":["Review tests"]}'
    )
    monkeypatch.setattr(
        "langgraph_maintenance_agent.graph._llm_client_for_state",
        lambda _state: client,
    )
    secret = "sk-or-abcdefghijklmnop"
    state: AgentState = {
        "use_llm": True,
        "provider": "openrouter",
        "selected_repos": [RepoConfig(name="demo", path=tmp_path, enabled=True)],
        "repo_results": [],
        "findings": [
            Finding(
                repo_name="demo",
                severity=Severity.HIGH,
                category=FindingCategory.SECURITY,
                title="Secret",
                description=secret,
            )
        ],
        "skipped_checks": [],
        "errors": [],
    }

    result = summarize_with_agent_node(state)

    assert result["summary"] == "Clean summary"
    assert secret not in client.messages[1]["content"]


def test_malformed_summary_falls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeSummaryClient('{"bad": true}')
    monkeypatch.setattr(
        "langgraph_maintenance_agent.graph._llm_client_for_state",
        lambda _state: client,
    )
    state: AgentState = {
        "use_llm": True,
        "provider": "openrouter",
        "selected_repos": [RepoConfig(name="demo", path=tmp_path, enabled=True)],
        "repo_results": [],
        "findings": [],
        "skipped_checks": [],
        "errors": [],
    }

    result = summarize_with_agent_node(state)

    assert result["summary"]
    assert any(error.stage == "summarize_with_agent" for error in result["errors"])


def test_failure_report_is_fresh_and_latest_not_reused(tmp_path: Path) -> None:
    output_dir = tmp_path / "reports"
    output_dir.mkdir()
    latest = output_dir / "latest.md"
    latest.write_text("old report", encoding="utf-8")

    with pytest.raises(ConfigError):
        run_workflow(
            config_path=tmp_path / "missing.yaml",
            output_dir=output_dir,
            dry_run=False,
            use_llm=False,
        )

    failure_reports = list(output_dir.glob("*-failure.md"))
    assert failure_reports
    failure_text = failure_reports[0].read_text(encoding="utf-8")
    assert "Normal repository inspection did not complete" in failure_text
    assert latest.read_text(encoding="utf-8") == "old report"
