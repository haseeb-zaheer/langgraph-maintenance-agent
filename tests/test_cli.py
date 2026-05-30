from __future__ import annotations

from pathlib import Path
from typing import Any

from langgraph_maintenance_agent import __version__
from langgraph_maintenance_agent.cli import main


def test_version_command(capsys) -> None:
    assert main(["version"]) == 0
    assert capsys.readouterr().out.strip() == __version__


def test_validate_config_placeholder_accepts_existing_file(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "repos.yaml"
    config_path.write_text(
        """
repos:
  - name: demo
    path: /path/to/demo
    enabled: true
    checks:
      - git-status
    safe_commands: {}
""",
        encoding="utf-8",
    )

    assert main(["validate-config", str(config_path)]) == 0
    assert "Config valid" in capsys.readouterr().out


def test_run_no_llm_dry_run_does_not_require_credentials(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
    config_path = tmp_path / "repos.yaml"
    config_path.write_text(
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

    assert main(["run", "--config", str(config_path), "--no-llm", "--dry-run"]) == 0
    assert "report not written" in capsys.readouterr().out


def test_run_llm_missing_key_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()
    config_path = tmp_path / "repos.yaml"
    config_path.write_text(
        f"""
repos:
  - name: demo
    path: {repo}
    enabled: true
""",
        encoding="utf-8",
    )

    try:
        main(["run", "--config", str(config_path), "--llm", "--dry-run"])
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("expected SystemExit")


def test_run_forced_discord_passes_override(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_run_workflow(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "repo_results": [],
            "findings": [],
            "report_path": "reports/latest.md",
            "discord_status": None,
        }

    monkeypatch.setattr(
        "langgraph_maintenance_agent.cli.run_workflow",
        fake_run_workflow,
    )

    assert (
        main(
            [
                "run",
                "--config",
                str(tmp_path / "repos.yaml"),
                "--no-llm",
                "--send-discord",
                "--summary-only",
                "--max-concurrency",
                "2",
            ]
        )
        == 0
    )
    assert captured["send_discord"] is True
    assert captured["summary_only"] is True
    assert captured["max_concurrency"] == 2


def test_run_no_discord_passes_override(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_run_workflow(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "repo_results": [],
            "findings": [],
            "report_path": "reports/latest.md",
            "discord_status": None,
        }

    monkeypatch.setattr(
        "langgraph_maintenance_agent.cli.run_workflow",
        fake_run_workflow,
    )

    assert (
        main(
            [
                "run",
                "--config",
                str(tmp_path / "repos.yaml"),
                "--no-llm",
                "--no-discord",
            ]
        )
        == 0
    )
    assert captured["send_discord"] is False


def test_send_command_reads_report_and_sends_summary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    report = tmp_path / "report.md"
    report.write_text(
        "# Routine Maintenance Report - 2026-05-30\n\n"
        "## Executive Summary\n\nEverything is fine.\n\n"
        "## Critical Findings\n\nNone found.\n\n"
        "## High Priority\n\nNone found.\n\n"
        "## Medium Priority\n\nNone found.\n\n"
        "## Suggested Next Actions\n\n- Keep watching.\n",
        encoding="utf-8",
    )
    captured: dict[str, str] = {}

    def fake_send(content: str) -> Any:
        captured["content"] = content
        return type("Result", (), {"messages_sent": 1})()

    monkeypatch.setattr(
        "langgraph_maintenance_agent.cli.send_discord_content",
        fake_send,
    )

    assert main(["send", str(report), "--summary-only"]) == 0
    assert "Everything is fine" in captured["content"]
    assert "Report path" in captured["content"]
