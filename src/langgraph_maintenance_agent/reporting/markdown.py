"""Markdown report rendering."""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from langgraph_maintenance_agent.config import RepoConfig
from langgraph_maintenance_agent.runtime.text import bound_text
from langgraph_maintenance_agent.schemas import (
    AgentError,
    CommandResult,
    Finding,
    FindingCategory,
    RepoResult,
    Severity,
    SkippedCheck,
)

REPORT_HEADINGS = [
    "Executive Summary",
    "Critical Findings",
    "High Priority",
    "Medium Priority",
    "Low Priority",
    "Repositories Scanned",
    "Repositories Skipped",
    "Dependency Concerns",
    "Bug Risk Review",
    "Refactor Opportunities",
    "Code Quality Notes",
    "Test Gap Notes",
    "Source Review Coverage",
    "Test/Lint/Build Results",
    "Command Results",
    "Dirty Worktrees",
    "Suggested Next Actions",
    "Appendix: Per-Repo Details",
]

SEVERITY_SECTION_MAP = {
    Severity.CRITICAL: "Critical Findings",
    Severity.HIGH: "High Priority",
    Severity.MEDIUM: "Medium Priority",
    Severity.LOW: "Low Priority",
    Severity.INFO: "Low Priority",
}


def render_report(
    *,
    run_id: str,
    started_at: str,
    dry_run: bool,
    selected_repos: list[RepoConfig],
    repo_results: list[RepoResult],
    findings: list[Finding],
    skipped_checks: list[SkippedCheck],
    errors: list[AgentError],
    summary: str | None,
    next_actions: list[str],
    redaction_count: int = 0,
    redaction_counts_by_type: dict[str, int] | None = None,
) -> str:
    """Render a polished local Markdown report from structured state."""

    report_date = _report_date(started_at)
    lines = [
        f"# Routine Maintenance Report - {report_date}",
        "",
        f"- Run ID: `{run_id}`",
        f"- Started: `{started_at}`",
        f"- Dry run: `{dry_run}`",
        "",
    ]
    if redaction_count:
        counts = redaction_counts_by_type or {}
        detail = ", ".join(f"{name}: {count}" for name, count in sorted(counts.items()))
        lines.extend(
            [
                "> Redaction warning: sensitive-looking content was redacted before "
                f"this report was persisted. Total redactions: {redaction_count}"
                + (f" ({detail})." if detail else "."),
                "",
            ]
        )

    sections: dict[str, list[str]] = {heading: [] for heading in REPORT_HEADINGS}
    sections["Executive Summary"].append(summary or "No summary generated.")

    findings_by_section = _group_findings(findings)
    for section in (
        "Critical Findings",
        "High Priority",
        "Medium Priority",
        "Low Priority",
    ):
        sections[section].extend(_render_findings(findings_by_section[section]))

    sections["Repositories Scanned"].extend(_render_scanned_repos(repo_results))
    sections["Repositories Skipped"].extend(
        _render_skipped_repos(selected_repos, repo_results, skipped_checks)
    )
    sections["Dependency Concerns"].extend(_render_dependency_concerns(findings))
    sections["Bug Risk Review"].extend(
        _render_category_findings(findings, FindingCategory.BUG_RISK)
    )
    sections["Refactor Opportunities"].extend(
        _render_category_findings(findings, FindingCategory.REFACTOR)
    )
    sections["Code Quality Notes"].extend(
        _render_category_findings(findings, FindingCategory.CODE_QUALITY)
    )
    sections["Test Gap Notes"].extend(
        _render_category_findings(findings, FindingCategory.TEST_GAP)
    )
    sections["Source Review Coverage"].extend(
        _render_source_review_coverage(repo_results)
    )
    command_results = _render_command_results(repo_results)
    sections["Test/Lint/Build Results"].extend(command_results)
    sections["Command Results"].extend(command_results)
    sections["Dirty Worktrees"].extend(_render_dirty_worktrees(findings))
    sections["Suggested Next Actions"].extend(_render_next_actions(next_actions))
    sections["Appendix: Per-Repo Details"].extend(
        _render_appendix(repo_results, skipped_checks, errors)
    )

    for heading in REPORT_HEADINGS:
        lines.extend([f"## {heading}", ""])
        content = sections[heading]
        lines.extend(content if content else ["None found."])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_failure_report(
    *,
    run_id: str | None,
    timestamp: str,
    stage: str,
    error_message: str,
    config_path: str,
) -> str:
    """Render a fresh failure report for runs that cannot complete normally."""

    return "\n".join(
        [
            f"# Routine Maintenance Failure Report - {_report_date(timestamp)}",
            "",
            f"- Run ID: `{run_id or 'unavailable'}`",
            f"- Timestamp: `{timestamp}`",
            f"- Stage: `{stage}`",
            f"- Config path: `{config_path}`",
            "",
            "Normal repository inspection did not complete. This report was "
            "generated for the failed run and is not copied to `latest.md`.",
            "",
            "## Error",
            "",
            error_message,
            "",
        ]
    )


def compact_discord_summary(
    report_markdown: str,
    report_path: str | None = None,
) -> str:
    """Extract a compact Discord-ready summary from a rendered report."""

    executive = _extract_section(report_markdown, "Executive Summary") or "None found."
    actions = (
        _extract_section(report_markdown, "Suggested Next Actions") or "None found."
    )
    severity_counts = {
        "critical": _section_item_count(report_markdown, "Critical Findings"),
        "high": _section_item_count(report_markdown, "High Priority"),
        "medium": _section_item_count(report_markdown, "Medium Priority"),
    }
    lines = [
        "**Routine Maintenance Report**",
        "",
        "**Executive Summary**",
        executive.strip(),
        "",
        "**Finding Counts**",
        (
            f"- Critical: {severity_counts['critical']}\n"
            f"- High: {severity_counts['high']}\n"
            f"- Medium: {severity_counts['medium']}"
        ),
        "",
        "**Next Actions**",
        actions.strip(),
    ]
    if report_path:
        lines.extend(["", f"Report path: `{report_path}`"])
    return "\n".join(lines)


def _report_date(started_at: str) -> str:
    try:
        return datetime.fromisoformat(started_at).date().isoformat()
    except ValueError:
        return started_at[:10] or "unknown"


def _group_findings(findings: list[Finding]) -> dict[str, list[Finding]]:
    grouped: dict[str, list[Finding]] = {
        "Critical Findings": [],
        "High Priority": [],
        "Medium Priority": [],
        "Low Priority": [],
    }
    for finding in findings:
        grouped[SEVERITY_SECTION_MAP[finding.severity]].append(finding)
    return grouped


def _render_findings(findings: list[Finding]) -> list[str]:
    lines: list[str] = []
    for finding in findings:
        lines.extend(
            [
                f"### `{finding.repo_name}` {finding.title}",
                "",
                finding.description,
            ]
        )
        if finding.category:
            lines.append(f"- Category: `{finding.category.value}`")
        if finding.command_label:
            lines.append(f"- Command: `{finding.command_label}`")
        if finding.evidence_paths:
            paths = ", ".join(f"`{path}`" for path in finding.evidence_paths[:8])
            lines.append(f"- Evidence: {paths}")
        if finding.suggested_action:
            lines.append(f"- Suggested action: {finding.suggested_action}")
        if finding.needs_human_review:
            lines.append("- Human review: required")
        lines.append("")
    return lines


def _render_scanned_repos(repo_results: list[RepoResult]) -> list[str]:
    return [
        f"- `{result.repo_name}`"
        + (f" ({result.path})" if result.path else "")
        + f": {len(result.findings)} finding(s), "
        f"{len(result.command_results)} command result(s)"
        for result in repo_results
    ]


def _render_skipped_repos(
    selected_repos: list[RepoConfig],
    repo_results: list[RepoResult],
    skipped_checks: list[SkippedCheck],
) -> list[str]:
    result_names = {result.repo_name for result in repo_results}
    lines = [
        f"- `{repo.name}`: inspection did not produce a result"
        for repo in selected_repos
        if repo.name not in result_names
    ]
    lines.extend(
        f"- `{item.repo_name}` `{item.check_name}`: {item.reason}"
        for item in skipped_checks
    )
    return lines


def _render_dependency_concerns(findings: list[Finding]) -> list[str]:
    return _render_category_findings(findings, FindingCategory.DEPENDENCY)


def _render_category_findings(
    findings: list[Finding],
    category: FindingCategory,
) -> list[str]:
    return _render_findings(
        [finding for finding in findings if finding.category == category]
    )


def _render_command_results(repo_results: list[RepoResult]) -> list[str]:
    lines: list[str] = []
    for result in repo_results:
        for command in result.command_results:
            lines.extend(_render_command_result(result.repo_name, command))
    return lines


def _render_command_result(repo_name: str, command: CommandResult) -> list[str]:
    lines = [
        f"### `{repo_name}` `{command.label}`",
        "",
        f"- Command: `{_command_label(command.command)}`",
        f"- Exit code: `{command.exit_code}`",
        f"- Timed out: `{command.timed_out}`",
        f"- Timeout seconds: `{command.timeout_seconds}`",
        f"- Duration seconds: `{command.duration_seconds}`",
        f"- Working directory: `{command.working_directory}`",
    ]
    for label, excerpt in (
        ("Stdout excerpt", command.stdout_excerpt),
        ("Stderr excerpt", command.stderr_excerpt),
    ):
        if excerpt:
            lines.extend(
                [
                    "",
                    f"{label}:",
                    "",
                    "```text",
                    bound_text(excerpt, 1200),
                    "```",
                ]
            )
    lines.append("")
    return lines


def _render_dirty_worktrees(findings: list[Finding]) -> list[str]:
    dirty = [
        finding
        for finding in findings
        if finding.category.value == "git"
        and "dirty" in f"{finding.title} {finding.description}".lower()
    ]
    return _render_findings(dirty)


def _render_next_actions(next_actions: list[str]) -> list[str]:
    return [f"- {action}" for action in next_actions]


def _render_appendix(
    repo_results: list[RepoResult],
    skipped_checks: list[SkippedCheck],
    errors: list[AgentError],
) -> list[str]:
    lines: list[str] = []
    skipped_by_repo: dict[str, list[SkippedCheck]] = {}
    for skipped in skipped_checks:
        skipped_by_repo.setdefault(skipped.repo_name, []).append(skipped)
    errors_by_repo: dict[str, list[AgentError]] = {}
    for error in errors:
        errors_by_repo.setdefault(error.repo_name or "workflow", []).append(error)

    for result in repo_results:
        severity_counts = Counter(finding.severity.value for finding in result.findings)
        counts = ", ".join(
            f"{severity}: {count}"
            for severity, count in sorted(severity_counts.items())
        )
        lines.extend(
            [
                f"### `{result.repo_name}`",
                "",
                f"- Path: `{result.path or 'unknown'}`",
                f"- Findings: {counts or 'none'}",
                f"- Commands: {len(result.command_results)}",
                f"- Tool calls: {result.metadata.tool_calls_made}",
                f"- Agent iterations: {result.metadata.iterations}",
            ]
        )
        if result.metadata.model_provider:
            lines.append(f"- Model provider: `{result.metadata.model_provider}`")
        if result.metadata.model_name:
            lines.append(f"- Model: `{result.metadata.model_name}`")
        for tool_call in result.metadata.tool_calls[:12]:
            detail = (
                f"- Tool `{tool_call.tool_name}`: {tool_call.status}"
                f" (arguments: {', '.join(tool_call.argument_keys) or 'none'}"
            )
            if tool_call.error_code:
                detail += f"; error: `{tool_call.error_code}`"
            lines.append(detail + ")")
        if result.metadata.source_review is not None:
            coverage = result.metadata.source_review
            lines.append(
                "- Source review planned: "
                + ", ".join(f"`{target.path}`" for target in coverage.planned)
                if coverage.planned
                else "- Source review planned: none"
            )
            lines.append(
                "- Source review read: "
                + ", ".join(f"`{item.path}`" for item in coverage.read)
                if coverage.read
                else "- Source review read: none"
            )
        for skipped in skipped_by_repo.get(result.repo_name, []):
            lines.append(f"- Skipped `{skipped.check_name}`: {skipped.reason}")
        for error in errors_by_repo.get(result.repo_name, []):
            lines.append(
                f"- Recoverable error at `{error.stage or 'unknown'}`: {error.message}"
            )
        lines.append("")
    for error in errors_by_repo.get("workflow", []):
        lines.append(
            f"- Workflow recoverable error at `{error.stage or 'unknown'}`: "
            f"{error.message}"
        )
    return lines


def _render_source_review_coverage(repo_results: list[RepoResult]) -> list[str]:
    lines: list[str] = []
    for result in repo_results:
        coverage = result.metadata.source_review
        if coverage is None:
            continue
        lines.extend(
            [
                f"### `{result.repo_name}`",
                "",
                f"- Candidate files: {coverage.candidate_files}",
                f"- Planned files: {coverage.planned_files}",
                f"- Files read: {coverage.read_files}",
                f"- Bytes read: {coverage.bytes_read}",
                f"- Skipped planned files: {coverage.skipped_files}",
                f"- Generated files skipped: {coverage.generated_files_skipped}",
                f"- Review mode: `{coverage.review_mode}`",
                f"- Validation status: `{coverage.validation_status}`",
                f"- Repair attempted: `{coverage.repair_attempted}`",
            ]
        )
        if coverage.validation_error:
            lines.append(f"- Validation error: {coverage.validation_error}")
        if coverage.plan_rationale:
            lines.append(f"- Plan rationale: {coverage.plan_rationale}")
        if coverage.planned:
            planned = ", ".join(f"`{target.path}`" for target in coverage.planned)
            lines.append(f"- Planned paths: {planned}")
        if coverage.read:
            read = ", ".join(f"`{item.path}`" for item in coverage.read)
            lines.append(f"- Read paths: {read}")
        if coverage.skipped:
            skipped = ", ".join(
                f"`{item.path}` ({item.reason})" for item in coverage.skipped
            )
            lines.append(f"- Skipped paths: {skipped}")
        lines.append("")
    return lines


def _command_label(command: str | list[str]) -> str:
    if isinstance(command, str):
        return command
    return " ".join(command)


def _extract_section(markdown: str, heading: str) -> str:
    target = f"## {heading}"
    lines = markdown.splitlines()
    try:
        start = lines.index(target) + 1
    except ValueError:
        return ""
    while start < len(lines) and not lines[start].strip():
        start += 1
    end = start
    while end < len(lines) and not lines[end].startswith("## "):
        end += 1
    return "\n".join(lines[start:end]).strip()


def _section_item_count(markdown: str, heading: str) -> int:
    section = _extract_section(markdown, heading)
    if not section or section == "None found.":
        return 0
    return section.count("\n### ") + (1 if section.startswith("### ") else 0)
