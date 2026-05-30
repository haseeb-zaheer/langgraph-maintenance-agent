"""Static marker search tools."""

from __future__ import annotations

import re

from langgraph_maintenance_agent.runtime.text import bound_text
from langgraph_maintenance_agent.tools.files import _iter_public_files
from langgraph_maintenance_agent.tools.registry import ToolContext
from langgraph_maintenance_agent.tools.results import SearchMatch, ToolError, ToolResult
from langgraph_maintenance_agent.tools.safety import (
    contains_nul_bytes,
    iter_text_lines,
    redact_sensitive_lines,
)

MARKER_RE = re.compile(r"\b(TODO|FIXME|HACK)\b", re.IGNORECASE)


def search_static_markers(context: ToolContext, repo_name: str) -> ToolResult:
    """Search public-safe text files for common static maintenance markers."""

    try:
        root = context.repo_root(repo_name)
    except KeyError as exc:
        return ToolResult(
            tool_name="search_static_markers",
            repo_name=repo_name,
            ok=False,
            error=ToolError(code="unknown_repo", message=str(exc)),
        )
    matches: list[SearchMatch] = []
    for relative_path in _iter_public_files(root):
        path = root / relative_path
        if contains_nul_bytes(path):
            continue
        try:
            lines = iter_text_lines(path, context.limits.max_bytes_per_file)
        except OSError:
            continue
        for index, line in lines:
            marker = MARKER_RE.search(line)
            if marker is None:
                continue
            matches.append(
                SearchMatch(
                    path=relative_path.as_posix(),
                    line_number=index,
                    marker=marker.group(1).upper(),
                    line_excerpt=bound_text(redact_sensitive_lines(line).strip(), 240),
                )
            )
            if len(matches) >= context.limits.max_search_matches:
                return ToolResult(
                    tool_name="search_static_markers",
                    repo_name=repo_name,
                    ok=True,
                    data={
                        "matches": [match.model_dump() for match in matches],
                        "truncated": True,
                    },
                )
    return ToolResult(
        tool_name="search_static_markers",
        repo_name=repo_name,
        ok=True,
        data={"matches": [match.model_dump() for match in matches], "truncated": False},
    )
