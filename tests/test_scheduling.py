from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_scripts_pass_bash_syntax() -> None:
    subprocess.run(
        [
            "bash",
            "-n",
            "scripts/run_maintenance_check.sh",
            "scripts/run_and_send.sh",
            "scripts/install_systemd_user_units.sh",
        ],
        cwd=ROOT,
        check=True,
    )


def test_script_failure_path_does_not_echo_secrets() -> None:
    placeholder_token = "sk-or-test-placeholder-value"
    env = {
        **os.environ,
        "LANGGRAPH_MAINTENANCE_CONFIG": "/tmp/missing-maintenance-config.yaml",
        "LANGGRAPH_MAINTENANCE_TIMEOUT_SECONDS": "30",
        "OPENROUTER_API_KEY": placeholder_token,
        "LANGGRAPH_MAINTENANCE_DISCORD_WEBHOOK_URL": (
            "https://discord.com/api/" + "webhooks/123/token"
        ),
    }

    result = subprocess.run(
        ["bash", "scripts/run_maintenance_check.sh"],
        cwd=ROOT,
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    combined_output = result.stdout + result.stderr
    assert placeholder_token not in combined_output
    assert "discord.com/api/" + "webhooks" not in combined_output
    assert list((ROOT / "reports").glob("*-failure.md"))


def test_systemd_units_are_template_based() -> None:
    service = (ROOT / "systemd/langgraph-maintenance-agent.service").read_text(
        encoding="utf-8"
    )
    timer = (ROOT / "systemd/langgraph-maintenance-agent.timer").read_text(
        encoding="utf-8"
    )

    assert "WorkingDirectory={{PROJECT_DIR}}" in service
    assert "EnvironmentFile=-{{PROJECT_DIR}}/.env" in service
    assert "ExecStart={{PROJECT_DIR}}/scripts/run_and_send.sh" in service
    assert "/home/haseeb/" not in service
    assert "OnCalendar=*-*-* 11:00:00" in timer
    assert "Persistent=true" in timer


def test_systemd_install_helper_substitutes_current_clone_path() -> None:
    install_script = ROOT / "scripts/install_systemd_user_units.sh"
    subprocess.run(["bash", "-n", str(install_script)], cwd=ROOT, check=True)

    service_template = (ROOT / "systemd/langgraph-maintenance-agent.service").read_text(
        encoding="utf-8"
    )
    rendered_service = service_template.replace("{{PROJECT_DIR}}", str(ROOT))

    assert f"WorkingDirectory={ROOT}" in rendered_service
    assert f"ExecStart={ROOT}/scripts/run_and_send.sh" in rendered_service
