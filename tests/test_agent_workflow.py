from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from langgraph_maintenance_agent.agents.repo_inspector import RepoInspectorAgent
from langgraph_maintenance_agent.config import AppConfig, CheckName, RepoConfig
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
from langgraph_maintenance_agent.schemas import (
    CommandResult,
    Finding,
    FindingCategory,
    RepoResult,
    Severity,
)
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


def test_agent_requires_evidence_tools_before_structured_output(
    tmp_path: Path,
) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial"], cwd=tmp_path, check=True
    )
    payload = {
        "repo_name": "demo",
        "summary": "premature",
        "findings": [],
    }
    repo = RepoConfig(
        name="demo",
        path=tmp_path,
        enabled=True,
        checks=[CheckName.GIT_STATUS],
    )
    agent = RepoInspectorAgent(
        tool_registry=registry_for_repos([repo]),
        llm_client=FakeClient(
            [
                ChatCompletionResult(content=json.dumps(payload), raw={}),
                ChatCompletionResult(
                    tool_calls=[
                        ChatToolCall(
                            id="1",
                            name="git_status",
                            arguments={"repo_name": "demo"},
                        ),
                        ChatToolCall(
                            id="2",
                            name="latest_commit",
                            arguments={"repo_name": "demo"},
                        ),
                    ],
                    raw={},
                ),
                ChatCompletionResult(content=json.dumps(payload), raw={}),
            ]
        ),  # type: ignore[arg-type]
    )

    result = agent.inspect(repo)

    assert not result.errors


def test_agent_marks_incomplete_when_model_never_calls_required_tools(
    tmp_path: Path,
) -> None:
    payload = {
        "repo_name": "demo",
        "summary": "premature",
        "findings": [],
    }
    repo = RepoConfig(
        name="demo",
        path=tmp_path,
        enabled=True,
        checks=[CheckName.GIT_STATUS],
    )
    agent = RepoInspectorAgent(
        tool_registry=registry_for_repos([repo]),
        llm_client=FakeClient(
            [
                ChatCompletionResult(content=json.dumps(payload), raw={}),
                ChatCompletionResult(content=json.dumps(payload), raw={}),
            ]
        ),  # type: ignore[arg-type]
        max_iterations=2,
    )

    result = agent.inspect(repo)

    assert result.errors
    assert "maximum agent iteration limit" in result.errors[0].message


def test_agent_ignores_fabricated_command_results(tmp_path: Path) -> None:
    payload = {
        "repo_name": "demo",
        "summary": "fabricated command",
        "findings": [],
        "command_results": [
            {
                "label": "tests",
                "command": ["python", "-m", "pytest"],
                "working_directory": str(tmp_path),
                "exit_code": 1,
                "timed_out": False,
                "stdout_excerpt": "fabricated",
                "stderr_excerpt": "fabricated",
                "duration_seconds": 0.1,
                "timeout_seconds": 300,
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

    assert result.command_results == []
    assert not any(finding.command_label == "tests" for finding in result.findings)


def test_agent_records_actual_command_tool_result(tmp_path: Path) -> None:
    repo = RepoConfig(
        name="demo",
        path=tmp_path,
        enabled=True,
        checks=[CheckName.TESTS],
        safe_commands={"tests": f"{sys.executable} -m pytest --version"},
    )
    payload = {
        "repo_name": "demo",
        "summary": "done",
        "findings": [],
        "command_results": [],
    }
    agent = RepoInspectorAgent(
        tool_registry=registry_for_repos([repo]),
        llm_client=FakeClient(
            [
                ChatCompletionResult(
                    tool_calls=[
                        ChatToolCall(
                            id="1",
                            name="run_configured_safe_command",
                            arguments={
                                "repo_name": "demo",
                                "command_label": "tests",
                            },
                        )
                    ],
                    raw={},
                ),
                ChatCompletionResult(content=json.dumps(payload), raw={}),
            ]
        ),  # type: ignore[arg-type]
    )

    result = agent.inspect(repo)

    assert len(result.command_results) == 1
    assert result.command_results[0].label == "tests"
    assert result.command_results[0].exit_code == 0


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


def test_no_llm_workflow_inspects_two_repos(tmp_path: Path) -> None:
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()
    (repo_a / "README.md").write_text("# A\n", encoding="utf-8")
    (repo_b / "README.md").write_text("# B\n", encoding="utf-8")
    config = tmp_path / "repos.yaml"
    config.write_text(
        f"""
repos:
  - name: repo-a
    path: {repo_a}
    enabled: true
  - name: repo-b
    path: {repo_b}
    enabled: true
report:
  output_dir: {tmp_path / "reports"}
""",
        encoding="utf-8",
    )

    state = run_workflow(config_path=config, dry_run=True, use_llm=False)

    assert [result.repo_name for result in state["repo_results"]] == [
        "repo-a",
        "repo-b",
    ]


def test_no_llm_workflow_includes_configured_command_results(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config = tmp_path / "repos.yaml"
    config.write_text(
        f"""
repos:
  - name: demo
    path: {repo}
    enabled: true
    checks:
      - tests
    safe_commands:
      tests: {sys.executable} -m pytest --version
report:
  output_dir: {tmp_path / "reports"}
""",
        encoding="utf-8",
    )

    state = run_workflow(config_path=config, dry_run=True, use_llm=False)

    result = state["repo_results"][0]
    assert len(result.command_results) == 1
    assert result.command_results[0].label == "tests"
    assert result.command_results[0].exit_code == 0


def test_no_llm_nonzero_command_becomes_finding(tmp_path: Path) -> None:
    agent = RepoInspectorAgent(
        tool_registry=registry_for_repos(
            [
                RepoConfig(
                    name="demo",
                    path=tmp_path,
                    enabled=True,
                    checks=[CheckName.TESTS],
                    safe_commands={
                        "tests": f"{sys.executable} -m pytest missing_test_file.py"
                    },
                )
            ]
        )
    )

    result = agent.inspect_without_llm(
        RepoConfig(
            name="demo",
            path=tmp_path,
            enabled=True,
            checks=[CheckName.TESTS],
            safe_commands={"tests": f"{sys.executable} -m pytest missing_test_file.py"},
        )
    )

    assert result.command_results[0].exit_code not in (None, 0)
    assert any(
        finding.title == "tests command failed"
        and finding.command_label == "tests"
        and finding.needs_human_review
        for finding in result.findings
    )


def test_command_style_check_without_safe_command_is_skipped(tmp_path: Path) -> None:
    agent = RepoInspectorAgent(tool_registry=registry_for(tmp_path))
    repo = RepoConfig(
        name="demo",
        path=tmp_path,
        enabled=True,
        checks=[CheckName.TESTS],
        safe_commands={},
    )

    result = agent.inspect_without_llm(repo)

    assert not result.command_results
    assert any(
        skipped.check_name == "tests"
        and "No safe_commands entry configured" in skipped.reason
        for skipped in result.skipped_checks
    )


def test_no_llm_workflow_continues_when_repo_path_is_missing(tmp_path: Path) -> None:
    existing_repo = tmp_path / "existing"
    existing_repo.mkdir()
    config = tmp_path / "repos.yaml"
    config.write_text(
        f"""
repos:
  - name: missing
    path: {tmp_path / "missing"}
    enabled: true
  - name: existing
    path: {existing_repo}
    enabled: true
report:
  output_dir: {tmp_path / "reports"}
""",
        encoding="utf-8",
    )

    state = run_workflow(config_path=config, dry_run=True, use_llm=False)

    assert [result.repo_name for result in state["repo_results"]] == [
        "missing",
        "existing",
    ]
    missing_result = state["repo_results"][0]
    assert missing_result.findings
    assert any(
        "does not exist" in finding.description
        for finding in missing_result.findings
    )


def test_no_llm_workflow_writes_report_and_latest(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config = tmp_path / "repos.yaml"
    output_dir = tmp_path / "reports"
    config.write_text(
        f"""
repos:
  - name: demo
    path: {repo}
    enabled: true
report:
  output_dir: {output_dir}
""",
        encoding="utf-8",
    )

    state = run_workflow(config_path=config, dry_run=False, use_llm=False)

    assert state["report_path"] is not None
    report_path = Path(state["report_path"])
    assert report_path.exists()
    assert (output_dir / "latest.md").read_text(
        encoding="utf-8"
    ) == report_path.read_text(encoding="utf-8")


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


def test_report_includes_redacted_command_results(tmp_path: Path) -> None:
    config = AppConfig(
        repos=[RepoConfig(name="demo", path=tmp_path, enabled=True)],
    )
    secret_key = "sk-" + "b" * 20
    state: AgentState = {
        "config": config,
        "output_dir": str(tmp_path / "reports"),
        "started_at": "2026-05-30T00:00:00+00:00",
        "run_id": "test",
        "dry_run": False,
        "findings": [],
        "skipped_checks": [],
        "summary": "summary",
        "repo_results": [
            RepoResult(
                repo_name="demo",
                path=str(tmp_path),
                command_results=[
                    CommandResult(
                        label="tests",
                        command=["python", "-c", "print('ok')"],
                        working_directory=str(tmp_path),
                        exit_code=0,
                        timed_out=False,
                        stdout_excerpt=f"ok {secret_key}",
                        stderr_excerpt="",
                        duration_seconds=0.01,
                        timeout_seconds=300,
                    )
                ],
            )
        ],
    }

    rendered = render_markdown_node(state)
    redacted = redact_report_node(rendered)
    written = write_report_node(redacted)

    report_text = Path(written["report_path"]).read_text(encoding="utf-8")
    assert "## Command Results" in report_text
    assert "`demo` `tests`" in report_text
    assert secret_key not in report_text
    assert "[redacted]" in report_text
