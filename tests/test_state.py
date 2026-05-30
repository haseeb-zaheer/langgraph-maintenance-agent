from __future__ import annotations

from langgraph_maintenance_agent.state import AgentState


def test_agent_state_is_json_safe_shape() -> None:
    state: AgentState = {
        "run_id": "run-1",
        "started_at": "2026-01-01T00:00:00Z",
        "config_path": "examples/repos.yaml",
        "repos": [],
        "repo_results": [],
        "findings": [],
        "skipped_checks": [],
        "report_markdown": None,
        "report_path": None,
        "discord_status": None,
        "errors": [],
    }

    assert state["run_id"] == "run-1"
