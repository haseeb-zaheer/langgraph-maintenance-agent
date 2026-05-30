"""LangGraph workflow assembly."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from shutil import copyfile
from typing import Any, cast

from langgraph.graph import END, StateGraph

from langgraph_maintenance_agent.agents.repo_inspector import RepoInspectorAgent
from langgraph_maintenance_agent.config import ConfigError, load_config
from langgraph_maintenance_agent.llm.openrouter import OpenRouterClient
from langgraph_maintenance_agent.reporting.redaction import redact_text
from langgraph_maintenance_agent.runtime.paths import (
    choose_report_path,
    ensure_output_dir,
    latest_report_path,
)
from langgraph_maintenance_agent.schemas import (
    AgentError,
    Finding,
    RepoResult,
    SkippedCheck,
)
from langgraph_maintenance_agent.state import AgentState
from langgraph_maintenance_agent.tools import (
    build_tool_registry as build_default_tool_registry,
)
from langgraph_maintenance_agent.tools.registry import ToolContext, ToolRegistry


def load_config_node(state: AgentState) -> AgentState:
    """Load and validate config from state config_path."""

    config_path = Path(state["config_path"])
    config = load_config(config_path)
    return {**state, "config": config, "repos": config.repos}


def prepare_run_node(state: AgentState) -> AgentState:
    """Create run metadata and resolve output directory."""

    now = datetime.now(UTC)
    config = state["config"]
    output_dir_value = state.get("output_dir")
    output_dir = (
        Path(output_dir_value) if output_dir_value else config.report.output_dir
    )
    return {
        **state,
        "run_id": now.strftime("%Y%m%d%H%M%S"),
        "started_at": now.isoformat(),
        "output_dir": str(output_dir),
        "repo_results": [],
        "findings": [],
        "skipped_checks": [],
        "errors": [],
    }


def select_repos_node(state: AgentState) -> AgentState:
    """Select enabled repos from validated config."""

    repos = [repo for repo in state["repos"] if repo.enabled]
    return {**state, "selected_repos": repos}


def build_tool_registry_node(state: AgentState) -> AgentState:
    """Build the repo-scoped safe tool registry."""

    config = state["config"]
    context = ToolContext.from_config(config)
    return {**state, "tool_registry": build_default_tool_registry(context)}


def _llm_client_for_state(state: AgentState) -> OpenRouterClient | None:
    if not state.get("use_llm", False):
        return None
    provider = state.get("provider", "openrouter")
    if provider != "openrouter":
        raise ConfigError(f"unsupported LLM provider: {provider}")
    return OpenRouterClient()


def inspect_repo_agent_node(state: AgentState) -> AgentState:
    """Run the repo inspector sequentially for selected repos."""

    registry = cast(ToolRegistry, state["tool_registry"])
    llm_client = _llm_client_for_state(state)
    agent = RepoInspectorAgent(
        tool_registry=registry,
        llm_client=llm_client,
        max_tool_calls=state.get("max_tool_calls", 12),
        max_iterations=state.get("max_agent_iterations", 6),
    )
    results = [agent.inspect(repo) for repo in state.get("selected_repos", [])]
    return {**state, "repo_results": results}


def normalize_agent_output_node(state: AgentState) -> AgentState:
    """Validate normalized result collections from repo outputs."""

    normalized = [
        RepoResult.model_validate(result) for result in state.get("repo_results", [])
    ]
    return {**state, "repo_results": normalized}


def merge_results_node(state: AgentState) -> AgentState:
    """Merge findings and skipped checks across repositories."""

    findings: list[Finding] = []
    skipped: list[SkippedCheck] = []
    errors: list[AgentError] = []
    for result in state.get("repo_results", []):
        findings.extend(result.findings)
        skipped.extend(result.skipped_checks)
        errors.extend(result.errors)
    return {**state, "findings": findings, "skipped_checks": skipped, "errors": errors}


def summarize_fallback_node(state: AgentState) -> AgentState:
    """Create a deterministic summary for Batch 2 dry-run/public demo."""

    repos = state.get("selected_repos", [])
    findings = state.get("findings", [])
    errors = state.get("errors", [])
    summary = (
        f"Inspected {len(repos)} configured repo(s), found {len(findings)} finding(s), "
        f"and recorded {len(errors)} recoverable error(s)."
    )
    next_actions = [
        "Review high and medium severity findings first.",
        "Enable LLM mode with OpenRouter when credentials are available.",
    ]
    return {**state, "summary": summary, "next_actions": next_actions}


def render_markdown_node(state: AgentState) -> AgentState:
    """Render a simple Markdown report."""

    lines = [
        "# Routine Maintenance Report",
        "",
        f"- Run ID: {state.get('run_id', 'unknown')}",
        f"- Started: {state.get('started_at', 'unknown')}",
        f"- Dry run: {state.get('dry_run', False)}",
        "",
        "## Summary",
        "",
        state.get("summary") or "No summary generated.",
        "",
        "## Findings",
        "",
    ]
    findings = state.get("findings", [])
    if findings:
        for finding in findings:
            lines.extend(
                [
                    (
                        f"### [{finding.severity.value}] "
                        f"{finding.repo_name}: {finding.title}"
                    ),
                    "",
                    finding.description,
                    "",
                ]
            )
    else:
        lines.extend(["No findings.", ""])
    lines.extend(["## Skipped Checks", ""])
    skipped = state.get("skipped_checks", [])
    if skipped:
        for item in skipped:
            lines.append(f"- `{item.repo_name}` `{item.check_name}`: {item.reason}")
    else:
        lines.append("No skipped checks.")
    lines.append("")
    return {**state, "report_markdown": "\n".join(lines)}


def redact_report_node(state: AgentState) -> AgentState:
    """Redact report content before persistence."""

    report_markdown = state.get("report_markdown")
    if report_markdown is None:
        return state
    return {**state, "report_markdown": redact_text(report_markdown)}


def write_report_node(state: AgentState) -> AgentState:
    """Write the report unless dry-run mode is active."""

    if state.get("dry_run", False):
        return {**state, "report_path": None}
    config = state["config"]
    output_dir = ensure_output_dir(Path(state["output_dir"] or "reports"))
    started = datetime.fromisoformat(state["started_at"])
    report_path = choose_report_path(
        output_dir,
        run_date=started.date(),
        run_at=started,
        filename_prefix=config.report.filename_prefix,
    )
    report_path.write_text(state.get("report_markdown") or "", encoding="utf-8")
    if config.report.update_latest:
        copyfile(report_path, latest_report_path(output_dir))
    return {**state, "report_path": str(report_path)}


def build_graph() -> Any:
    """Build the sequential Batch 2 LangGraph workflow."""

    graph = StateGraph(AgentState)
    graph.add_node("load_config", load_config_node)
    graph.add_node("prepare_run", prepare_run_node)
    graph.add_node("select_repos", select_repos_node)
    graph.add_node("build_tool_registry", build_tool_registry_node)
    graph.add_node("inspect_repo_agent", inspect_repo_agent_node)
    graph.add_node("normalize_agent_output", normalize_agent_output_node)
    graph.add_node("merge_results", merge_results_node)
    graph.add_node("summarize_with_agent", summarize_fallback_node)
    graph.add_node("render_markdown", render_markdown_node)
    graph.add_node("redact_report", redact_report_node)
    graph.add_node("write_report", write_report_node)
    graph.set_entry_point("load_config")
    graph.add_edge("load_config", "prepare_run")
    graph.add_edge("prepare_run", "select_repos")
    graph.add_edge("select_repos", "build_tool_registry")
    graph.add_edge("build_tool_registry", "inspect_repo_agent")
    graph.add_edge("inspect_repo_agent", "normalize_agent_output")
    graph.add_edge("normalize_agent_output", "merge_results")
    graph.add_edge("merge_results", "summarize_with_agent")
    graph.add_edge("summarize_with_agent", "render_markdown")
    graph.add_edge("render_markdown", "redact_report")
    graph.add_edge("redact_report", "write_report")
    graph.add_edge("write_report", END)
    return graph.compile()


def run_workflow(
    *,
    config_path: Path,
    output_dir: Path | None = None,
    dry_run: bool = False,
    use_llm: bool = False,
    provider: str = "openrouter",
    max_tool_calls: int = 12,
    max_agent_iterations: int = 6,
) -> AgentState:
    """Run the sequential workflow and return final state."""

    graph = build_graph()
    initial: AgentState = {
        "config_path": str(config_path),
        "output_dir": str(output_dir) if output_dir is not None else None,
        "dry_run": dry_run,
        "use_llm": use_llm,
        "provider": provider,
        "max_tool_calls": max_tool_calls,
        "max_agent_iterations": max_agent_iterations,
    }
    return cast(AgentState, graph.invoke(initial))
