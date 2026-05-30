from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langgraph_maintenance_agent.agents.repo_inspector import RepoInspectorAgent
from langgraph_maintenance_agent.config import AppConfig, RepoConfig
from langgraph_maintenance_agent.graph import (
    redact_report_node,
    render_markdown_node,
    run_workflow,
    write_report_node,
)
from langgraph_maintenance_agent.llm.openrouter import (
    ChatCompletionResult,
    ChatToolCall,
)
from langgraph_maintenance_agent.schemas import Finding, FindingCategory, Severity
from langgraph_maintenance_agent.state import AgentState
from langgraph_maintenance_agent.tools import build_tool_registry
from langgraph_maintenance_agent.tools.registry import ToolContext


class FakeClient:
    def __init__(self, responses: list[ChatCompletionResult]) -> None:
        self.responses = responses

    def chat(self, **_: Any) -> ChatCompletionResult:
        return self.responses.pop(0)


def registry_for(tmp_path: Path):
    config = AppConfig(repos=[RepoConfig(name="demo", path=tmp_path, enabled=True)])
    return build_tool_registry(ToolContext.from_config(config))


def registry_for_repos(repos: list[RepoConfig]):
    config = AppConfig(repos=repos)
    return build_tool_registry(ToolContext.from_config(config))


def test_agent_cannot_execute_unregistered_tool(tmp_path: Path) -> None:
    agent = RepoInspectorAgent(
        tool_registry=registry_for(tmp_path),
        llm_client=FakeClient(
            [
                ChatCompletionResult(
                    tool_calls=[
                        ChatToolCall(
                            id="1", name="shell", arguments={"repo_name": "demo"}
                        )
                    ],
                    raw={},
                )
            ]
        ),  # type: ignore[arg-type]
    )

    result = agent.inspect(RepoConfig(name="demo", path=tmp_path, enabled=True))

    assert result.errors
    assert "unregistered tool" in result.errors[0].message


def test_agent_tool_limit_produces_incomplete_result(tmp_path: Path) -> None:
    agent = RepoInspectorAgent(
        tool_registry=registry_for(tmp_path),
        llm_client=FakeClient(
            [
                ChatCompletionResult(
                    tool_calls=[
                        ChatToolCall(
                            id="1", name="list_files", arguments={"repo_name": "demo"}
                        )
                    ],
                    raw={},
                )
            ]
        ),  # type: ignore[arg-type]
        max_tool_calls=0,
    )

    result = agent.inspect(RepoConfig(name="demo", path=tmp_path, enabled=True))

    assert result.errors
    assert "maximum tool call limit" in result.errors[0].message


def test_agent_rejects_tool_call_for_different_repo(tmp_path: Path) -> None:
    repo_a = tmp_path / "a"
    repo_b = tmp_path / "b"
    repo_a.mkdir()
    repo_b.mkdir()
    agent = RepoInspectorAgent(
        tool_registry=registry_for_repos(
            [
                RepoConfig(name="repo-a", path=repo_a, enabled=True),
                RepoConfig(name="repo-b", path=repo_b, enabled=True),
            ]
        ),
        llm_client=FakeClient(
            [
                ChatCompletionResult(
                    tool_calls=[
                        ChatToolCall(
                            id="1",
                            name="list_files",
                            arguments={"repo_name": "repo-b"},
                        )
                    ],
                    raw={},
                )
            ]
        ),  # type: ignore[arg-type]
    )

    result = agent.inspect(RepoConfig(name="repo-a", path=repo_a, enabled=True))

    assert result.repo_name == "repo-a"
    assert result.errors
    assert "different repo" in result.errors[0].message


def test_agent_malformed_model_output_produces_incomplete_result(
    tmp_path: Path,
) -> None:
    agent = RepoInspectorAgent(
        tool_registry=registry_for(tmp_path),
        llm_client=FakeClient([ChatCompletionResult(content='{"bad": true}', raw={})]),  # type: ignore[arg-type]
    )

    result = agent.inspect(RepoConfig(name="demo", path=tmp_path, enabled=True))

    assert result.errors
    assert "malformed structured output" in result.errors[0].message


def test_agent_rejects_structured_output_for_wrong_repo(tmp_path: Path) -> None:
    payload = {
        "repo_name": "other",
        "summary": "wrong repo",
        "findings": [],
    }
    agent = RepoInspectorAgent(
        tool_registry=registry_for(tmp_path),
        llm_client=FakeClient(
            [ChatCompletionResult(content=json.dumps(payload), raw={})]
        ),  # type: ignore[arg-type]
    )

    result = agent.inspect(RepoConfig(name="demo", path=tmp_path, enabled=True))

    assert result.errors
    assert "unexpected repo_name" in result.errors[0].message


def test_agent_rejects_finding_for_wrong_repo(tmp_path: Path) -> None:
    payload = {
        "repo_name": "demo",
        "summary": "wrong finding repo",
        "findings": [
            {
                "repo_name": "other",
                "severity": Severity.INFO.value,
                "category": FindingCategory.DOCS.value,
                "title": "Docs",
                "description": "Wrong repo.",
            }
        ],
    }
    agent = RepoInspectorAgent(
        tool_registry=registry_for(tmp_path),
        llm_client=FakeClient(
            [ChatCompletionResult(content=json.dumps(payload), raw={})]
        ),  # type: ignore[arg-type]
    )

    result = agent.inspect(RepoConfig(name="demo", path=tmp_path, enabled=True))

    assert result.errors
    assert "finding used unexpected repo_name" in result.errors[0].message


def test_agent_accepts_structured_output(tmp_path: Path) -> None:
    payload = {
        "repo_name": "demo",
        "summary": "ok",
        "findings": [
            {
                "repo_name": "demo",
                "severity": Severity.INFO.value,
                "category": FindingCategory.DOCS.value,
                "title": "Docs present",
                "description": "README exists.",
            }
        ],
    }
    agent = RepoInspectorAgent(
        tool_registry=registry_for(tmp_path),
        llm_client=FakeClient(
            [ChatCompletionResult(content=json.dumps(payload), raw={})]
        ),  # type: ignore[arg-type]
    )

    result = agent.inspect(RepoConfig(name="demo", path=tmp_path, enabled=True))

    assert len(result.findings) == 1


def test_no_llm_workflow_dry_run_writes_no_reports(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
    config = tmp_path / "repos.yaml"
    config.write_text(
        f"""
repos:
  - name: demo
    path: {repo}
    enabled: true
    checks:
      - git-status
report:
  output_dir: {tmp_path / "reports"}
""",
        encoding="utf-8",
    )

    state = run_workflow(config_path=config, dry_run=True, use_llm=False)

    assert state["report_path"] is None
    assert not (tmp_path / "reports").exists()
    assert state["repo_results"]


def test_report_redaction_runs_before_report_and_latest_write(tmp_path: Path) -> None:
    config = AppConfig(
        repos=[RepoConfig(name="demo", path=tmp_path, enabled=True)],
    )
    secret_key = "sk-" + "a" * 20
    bearer_header = "Authorization: " + "Bearer secret-token"
    finding = Finding(
        repo_name="demo",
        severity=Severity.HIGH,
        category=FindingCategory.SECURITY,
        title=f"Leaked token {secret_key}",
        description=f"Header: {bearer_header}",
    )
    state: AgentState = {
        "config": config,
        "output_dir": str(tmp_path / "reports"),
        "started_at": "2026-05-30T00:00:00+00:00",
        "run_id": "test",
        "dry_run": False,
        "findings": [finding],
        "skipped_checks": [],
        "summary": "summary",
    }

    rendered = render_markdown_node(state)
    redacted = redact_report_node(rendered)
    written = write_report_node(redacted)

    assert written["report_path"] is not None
    report_text = Path(written["report_path"]).read_text(encoding="utf-8")
    latest_text = (tmp_path / "reports" / "latest.md").read_text(encoding="utf-8")
    assert secret_key not in report_text
    assert "secret-token" not in report_text
    assert "[redacted]" in report_text
    assert report_text == latest_text
