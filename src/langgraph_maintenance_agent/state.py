"""LangGraph state definitions."""

from __future__ import annotations

from typing import TypedDict

from langgraph_maintenance_agent.config import AppConfig, RepoConfig
from langgraph_maintenance_agent.schemas import (
    AgentError,
    DeliveryStatus,
    Finding,
    RepoResult,
    SkippedCheck,
)


class AgentState(TypedDict, total=False):
    """Serializable workflow state shared by LangGraph nodes."""

    run_id: str
    started_at: str
    config_path: str
    config: AppConfig
    tool_registry: object
    output_dir: str | None
    dry_run: bool
    use_llm: bool
    provider: str
    max_tool_calls: int
    max_agent_iterations: int
    repos: list[RepoConfig]
    selected_repos: list[RepoConfig]
    repo_results: list[RepoResult]
    findings: list[Finding]
    skipped_checks: list[SkippedCheck]
    summary: str | None
    next_actions: list[str]
    report_markdown: str | None
    report_path: str | None
    discord_status: DeliveryStatus | None
    errors: list[AgentError]
