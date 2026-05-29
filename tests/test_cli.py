from __future__ import annotations

from pathlib import Path

from langgraph_maintenance_agent import __version__
from langgraph_maintenance_agent.cli import main


def test_version_command(capsys) -> None:
    assert main(["version"]) == 0
    assert capsys.readouterr().out.strip() == __version__


def test_validate_config_placeholder_accepts_existing_file(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "repos.yaml"
    config_path.write_text("repos: []\n", encoding="utf-8")

    assert main(["validate-config", str(config_path)]) == 0
    assert "Config file exists" in capsys.readouterr().out
