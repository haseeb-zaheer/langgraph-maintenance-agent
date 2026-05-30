"""LangGraph workflow assembly."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from shutil import copyfile
from typing import Any, cast

from langgraph.graph import END, StateGraph
from langgraph.types import Send

from langgraph_maintenance_agent.agents.prompts import (
    SUMMARY_SYSTEM_PROMPT,
    summary_user_prompt,
)
from langgraph_maintenance_agent.agents.repo_inspector import RepoInspectorAgent
from langgraph_maintenance_agent.config import ConfigError, load_config
from langgraph_maintenance_agent.llm.openrouter import OpenRouterClient
from langgraph_maintenance_agent.reporting.discord import (
    DiscordDeliveryError,
    send_discord_content,
)
from langgraph_maintenance_agent.reporting.markdown import (
    compact_discord_summary,
    render_failure_report,
    render_report,
)
from langgraph_maintenance_agent.reporting.redaction import (
    redact_text,
    redact_text_with_metadata,
)
from langgraph_maintenance_agent.runtime.paths import (
    choose_report_path,
    ensure_output_dir,
    latest_report_path,
    timestamped_report_filename,
)
from langgraph_maintenance_agent.schemas import (
    AgentError,
    DeliveryStatus,
    Finding,
    RepoResult,
    SkippedCheck,
    SummaryOutput,
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
        "branch_results": [],
        "findings": [],
        "skipped_checks": [],
        "errors": [],
        "redaction_count": 0,
        "redaction_counts_by_type": {},
        "summary_only": state.get("summary_only", False),
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


def _tool_registry_for_repo(state: AgentState, repo_name: str) -> ToolRegistry:
    config = state["config"]
    repo = next(repo for repo in config.repos if repo.name == repo_name)
    branch_config = config.model_copy(update={"repos": [repo]})
    context = ToolContext.from_config(branch_config)
    return build_default_tool_registry(context)


def _llm_client_for_state(state: AgentState) -> OpenRouterClient | None:
    if not state.get("use_llm", False):
        return None
    provider = state.get("provider", "openrouter")
    if provider != "openrouter":
        raise ConfigError(f"unsupported LLM provider: {provider}")
    return OpenRouterClient()


def dispatch_repo_inspections(state: AgentState) -> list[Send] | str:
    """Fan out one isolated branch per selected repository."""

    repos = state.get("selected_repos", [])
    if not repos:
        return "normalize_agent_output"
    return [
        Send(
            "inspect_repo_branch",
            {
                **state,
                "current_repo": repo,
                "branch_results": [],
            },
        )
        for repo in repos
    ]


def inspect_repo_branch_node(state: AgentState) -> AgentState:
    """Run one repo inspector branch with a one-repo tool registry."""

    repo = state["current_repo"]
    try:
        registry = _tool_registry_for_repo(state, repo.name)
        llm_client = _llm_client_for_state(state)
        agent = RepoInspectorAgent(
            tool_registry=registry,
            llm_client=llm_client,
            max_tool_calls=state.get("max_tool_calls", 12),
            max_iterations=state.get("max_agent_iterations", 6),
        )
        result = agent.inspect(repo)
    except Exception as exc:
        result = RepoResult(
            repo_name=repo.name,
            path=str(repo.path) if repo.path is not None else None,
            errors=[
                AgentError(
                    message=f"repo inspection failed: {exc}",
                    repo_name=repo.name,
                    stage="inspect_repo_branch",
                    recoverable=not repo.required,
                )
            ],
        )
    return {"branch_results": [result]}


def normalize_agent_output_node(state: AgentState) -> AgentState:
    """Validate normalized result collections from repo outputs."""

    raw_results = state.get("branch_results") or state.get("repo_results", [])
    normalized = [RepoResult.model_validate(result) for result in raw_results]
    return {**state, "repo_results": normalized}


def merge_results_node(state: AgentState) -> AgentState:
    """Merge findings and skipped checks across repositories."""

    ordered_results = _order_repo_results(
        state.get("repo_results", []),
        state.get("selected_repos", []),
    )
    _raise_for_required_repo_failures(
        selected_repos=state.get("selected_repos", []),
        repo_results=ordered_results,
    )
    findings: list[Finding] = []
    skipped: list[SkippedCheck] = []
    errors: list[AgentError] = []
    for result in ordered_results:
        findings.extend(result.findings)
        skipped.extend(result.skipped_checks)
        errors.extend(result.errors)
    return {
        **state,
        "repo_results": ordered_results,
        "findings": findings,
        "skipped_checks": skipped,
        "errors": errors,
    }


def redact_structured_state_node(state: AgentState) -> AgentState:
    """Redact structured results before summary and rendering."""

    payload = {
        "repo_results": [
            result.model_dump(mode="json") for result in state.get("repo_results", [])
        ],
        "findings": [
            finding.model_dump(mode="json") for finding in state.get("findings", [])
        ],
        "skipped_checks": [
            skipped.model_dump(mode="json")
            for skipped in state.get("skipped_checks", [])
        ],
        "errors": [error.model_dump(mode="json") for error in state.get("errors", [])],
    }
    decoded, total_count, counts_by_type = _redact_json_compatible(payload)
    return {
        **state,
        "repo_results": [
            RepoResult.model_validate(item) for item in decoded["repo_results"]
        ],
        "findings": [Finding.model_validate(item) for item in decoded["findings"]],
        "skipped_checks": [
            SkippedCheck.model_validate(item) for item in decoded["skipped_checks"]
        ],
        "errors": [AgentError.model_validate(item) for item in decoded["errors"]],
        "redaction_count": state.get("redaction_count", 0) + total_count,
        "redaction_counts_by_type": _merge_counts(
            state.get("redaction_counts_by_type", {}),
            counts_by_type,
        ),
    }


def summarize_fallback_node(state: AgentState) -> AgentState:
    """Create a deterministic summary for no-LLM mode or fallback."""

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


def summarize_with_agent_node(state: AgentState) -> AgentState:
    """Summarize redacted structured results using LLM mode when enabled."""

    if not state.get("use_llm", False):
        return summarize_fallback_node(state)
    try:
        client = _llm_client_for_state(state)
        if client is None:
            return summarize_fallback_node(state)
        payload = json.dumps(
            {
                "repo_results": [
                    result.model_dump(mode="json")
                    for result in state.get("repo_results", [])
                ],
                "findings": [
                    finding.model_dump(mode="json")
                    for finding in state.get("findings", [])
                ],
                "skipped_checks": [
                    skipped.model_dump(mode="json")
                    for skipped in state.get("skipped_checks", [])
                ],
                "errors": [
                    error.model_dump(mode="json")
                    for error in state.get("errors", [])
                ],
            },
            sort_keys=True,
        )
        redacted_payload = redact_text(payload)
        response = client.chat(
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": summary_user_prompt(redacted_payload=redacted_payload),
                },
            ],
            response_schema=SummaryOutput.model_json_schema(),
        )
        output = SummaryOutput.model_validate_json(response.content or "")
        return {
            **state,
            "summary": output.executive_summary,
            "next_actions": output.next_actions,
        }
    except Exception as exc:
        fallback = summarize_fallback_node(state)
        errors = [
            *fallback.get("errors", []),
            AgentError(
                message=f"summary agent failed; deterministic fallback used: {exc}",
                stage="summarize_with_agent",
                recoverable=True,
            ),
        ]
        return {**fallback, "errors": errors}


def render_markdown_node(state: AgentState) -> AgentState:
    """Render a structured Markdown report."""

    return {
        **state,
        "report_markdown": render_report(
            run_id=state.get("run_id", "unknown"),
            started_at=state.get("started_at", "unknown"),
            dry_run=state.get("dry_run", False),
            selected_repos=state.get("selected_repos", []),
            repo_results=state.get("repo_results", []),
            findings=state.get("findings", []),
            skipped_checks=state.get("skipped_checks", []),
            errors=state.get("errors", []),
            summary=state.get("summary"),
            next_actions=state.get("next_actions", []),
            redaction_count=state.get("redaction_count", 0),
            redaction_counts_by_type=state.get("redaction_counts_by_type", {}),
        ),
    }


def redact_report_node(state: AgentState) -> AgentState:
    """Redact report content before persistence."""

    report_markdown = state.get("report_markdown")
    if report_markdown is None:
        return state
    redacted = redact_text_with_metadata(report_markdown)
    redacted_text = redacted.text
    if redacted.total_count and "Redaction warning:" not in redacted_text:
        redacted_text = _insert_redaction_warning(
            redacted_text,
            redaction_count=redacted.total_count,
            redaction_counts_by_type=redacted.counts_by_type,
        )
    return {
        **state,
        "report_markdown": redacted_text,
        "redaction_count": state.get("redaction_count", 0) + redacted.total_count,
        "redaction_counts_by_type": _merge_counts(
            state.get("redaction_counts_by_type", {}),
            redacted.counts_by_type,
        ),
    }


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


def send_discord_summary_node(state: AgentState) -> AgentState:
    """Optionally send the redacted report or compact summary to Discord."""

    enabled = state.get("send_discord")
    if enabled is None:
        enabled = state["config"].report.discord_enabled
    if state.get("dry_run", False) or not enabled:
        return {
            **state,
            "discord_status": DeliveryStatus(
                destination="discord",
                attempted=False,
                success=False,
                message="delivery disabled",
            ),
        }
    report_markdown = state.get("report_markdown") or ""
    content = (
        compact_discord_summary(report_markdown, state.get("report_path"))
        if state.get("summary_only", False)
        else report_markdown
    )
    try:
        result = send_discord_content(content)
    except DiscordDeliveryError as exc:
        return {
            **state,
            "discord_status": DeliveryStatus(
                destination="discord",
                attempted=True,
                success=False,
                message=str(exc),
            ),
        }
    return {
        **state,
        "discord_status": DeliveryStatus(
            destination="discord",
            attempted=True,
            success=True,
            message=f"sent {result.messages_sent} message(s)",
        ),
    }


def build_graph() -> Any:
    """Build the fan-out/fan-in LangGraph workflow."""

    graph = StateGraph(AgentState)
    graph.add_node("load_config", load_config_node)
    graph.add_node("prepare_run", prepare_run_node)
    graph.add_node("select_repos", select_repos_node)
    graph.add_node("inspect_repo_branch", inspect_repo_branch_node)
    graph.add_node("normalize_agent_output", normalize_agent_output_node)
    graph.add_node("merge_results", merge_results_node)
    graph.add_node("redact_structured_state", redact_structured_state_node)
    graph.add_node("summarize_with_agent", summarize_with_agent_node)
    graph.add_node("render_markdown", render_markdown_node)
    graph.add_node("redact_report", redact_report_node)
    graph.add_node("write_report", write_report_node)
    graph.add_node("send_discord_summary", send_discord_summary_node)
    graph.set_entry_point("load_config")
    graph.add_edge("load_config", "prepare_run")
    graph.add_edge("prepare_run", "select_repos")
    graph.add_conditional_edges("select_repos", dispatch_repo_inspections)
    graph.add_edge("inspect_repo_branch", "normalize_agent_output")
    graph.add_edge("normalize_agent_output", "merge_results")
    graph.add_edge("merge_results", "redact_structured_state")
    graph.add_edge("redact_structured_state", "summarize_with_agent")
    graph.add_edge("summarize_with_agent", "render_markdown")
    graph.add_edge("render_markdown", "redact_report")
    graph.add_edge("redact_report", "write_report")
    graph.add_edge("write_report", "send_discord_summary")
    graph.add_edge("send_discord_summary", END)
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
    max_concurrency: int = 4,
    send_discord: bool | None = None,
    summary_only: bool = False,
) -> AgentState:
    """Run the workflow and return final state."""

    graph = build_graph()
    initial: AgentState = {
        "config_path": str(config_path),
        "output_dir": str(output_dir) if output_dir is not None else None,
        "dry_run": dry_run,
        "use_llm": use_llm,
        "provider": provider,
        "max_tool_calls": max_tool_calls,
        "max_agent_iterations": max_agent_iterations,
        "max_concurrency": max_concurrency,
        "send_discord": send_discord,
        "summary_only": summary_only,
    }
    try:
        if use_llm:
            _llm_client_for_state(initial)
        return cast(
            AgentState,
            graph.invoke(initial, config={"max_concurrency": max_concurrency}),
        )
    except Exception as exc:
        _write_failure_report(
            config_path=config_path,
            output_dir=output_dir,
            dry_run=dry_run,
            stage="workflow",
            error_message=str(exc),
        )
        raise


def _write_failure_report(
    *,
    config_path: Path,
    output_dir: Path | None,
    dry_run: bool,
    stage: str,
    error_message: str,
) -> None:
    if dry_run:
        return
    now = datetime.now(UTC)
    resolved_output_dir = output_dir
    if resolved_output_dir is None:
        try:
            resolved_output_dir = load_config(config_path).report.output_dir
        except Exception:
            resolved_output_dir = Path("reports")
    target_dir = ensure_output_dir(resolved_output_dir)
    report_path = target_dir / timestamped_report_filename(now, "failure")
    redacted = redact_text(
        render_failure_report(
            run_id=now.strftime("%Y%m%d%H%M%S"),
            timestamp=now.isoformat(),
            stage=stage,
            error_message=error_message,
            config_path=str(config_path),
        )
    )
    report_path.write_text(redacted, encoding="utf-8")


def _merge_counts(
    left: dict[str, int],
    right: dict[str, int],
) -> dict[str, int]:
    merged = dict(left)
    for key, value in right.items():
        merged[key] = merged.get(key, 0) + value
    return merged


def _order_repo_results(
    repo_results: list[RepoResult],
    selected_repos: list[Any],
) -> list[RepoResult]:
    """Return branch results in config order, then any unexpected extras by name."""

    order = {repo.name: index for index, repo in enumerate(selected_repos)}
    return sorted(
        repo_results,
        key=lambda result: (order.get(result.repo_name, len(order)), result.repo_name),
    )


def _raise_for_required_repo_failures(
    *,
    selected_repos: list[Any],
    repo_results: list[RepoResult],
) -> None:
    """Fail the run after fan-in if any required repo did not inspect cleanly."""

    results_by_name = {result.repo_name: result for result in repo_results}
    failures: list[str] = []
    for repo in selected_repos:
        if not repo.required:
            continue
        result = results_by_name.get(repo.name)
        if result is None:
            failures.append(f"{repo.name}: inspection produced no result")
            continue
        if result.errors:
            messages = "; ".join(error.message for error in result.errors)
            failures.append(f"{repo.name}: {messages}")
            continue
        failed_tools = [
            finding.title
            for finding in result.findings
            if finding.category.value == "runtime"
            and "did not complete" in finding.title.lower()
        ]
        if failed_tools:
            failures.append(
                f"{repo.name}: required inspection tools failed: "
                + ", ".join(failed_tools)
            )
    if failures:
        raise RuntimeError("required repo inspection failed: " + " | ".join(failures))


def _redact_json_compatible(value: Any) -> tuple[Any, int, dict[str, int]]:
    """Redact string leaves while preserving JSON-compatible structure."""

    if isinstance(value, str):
        redacted = redact_text_with_metadata(value)
        return redacted.text, redacted.total_count, redacted.counts_by_type
    if isinstance(value, list):
        redacted_items: list[Any] = []
        list_total_count = 0
        list_counts_by_type: dict[str, int] = {}
        for item in value:
            redacted_item, item_count, item_counts = _redact_json_compatible(item)
            redacted_items.append(redacted_item)
            list_total_count += item_count
            list_counts_by_type = _merge_counts(list_counts_by_type, item_counts)
        return redacted_items, list_total_count, list_counts_by_type
    if isinstance(value, dict):
        redacted_dict: dict[Any, Any] = {}
        dict_total_count = 0
        dict_counts_by_type: dict[str, int] = {}
        for key, item in value.items():
            redacted_item, item_count, item_counts = _redact_json_compatible(item)
            redacted_dict[key] = redacted_item
            dict_total_count += item_count
            dict_counts_by_type = _merge_counts(dict_counts_by_type, item_counts)
        return redacted_dict, dict_total_count, dict_counts_by_type
    return value, 0, {}


def _insert_redaction_warning(
    report_markdown: str,
    *,
    redaction_count: int,
    redaction_counts_by_type: dict[str, int],
) -> str:
    detail = ", ".join(
        f"{name}: {count}" for name, count in sorted(redaction_counts_by_type.items())
    )
    warning = (
        "> Redaction warning: sensitive-looking content was redacted before "
        f"this report was persisted. Total redactions: {redaction_count}"
        + (f" ({detail})." if detail else ".")
    )
    lines = report_markdown.splitlines()
    insert_at = 0
    for index, line in enumerate(lines):
        if line.startswith("## "):
            insert_at = index
            break
    return "\n".join([*lines[:insert_at], warning, "", *lines[insert_at:]]) + "\n"
