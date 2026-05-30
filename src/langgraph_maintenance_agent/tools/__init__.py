"""Safe repository tool package."""

from __future__ import annotations

from functools import partial
from typing import Any

from langgraph_maintenance_agent.tools.commands import run_configured_safe_command
from langgraph_maintenance_agent.tools.dependencies import detect_dependency_manifests
from langgraph_maintenance_agent.tools.files import list_files, read_safe_file
from langgraph_maintenance_agent.tools.git import git_status, latest_commit
from langgraph_maintenance_agent.tools.registry import (
    RegisteredTool,
    ToolContext,
    ToolRegistry,
    repo_name_parameter,
)
from langgraph_maintenance_agent.tools.search import search_static_markers
from langgraph_maintenance_agent.tools.source import (
    list_source_files,
    read_source_file,
    read_source_files,
    summarize_source_tree,
)


def build_tool_registry(context: ToolContext) -> ToolRegistry:
    """Build the default safe tool registry for the configured repos."""

    repo_names = sorted(context.repos_by_name)
    repo_param = repo_name_parameter(repo_names)

    def params(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
        merged = {"repo_name": repo_param, **properties}
        return {
            "type": "object",
            "properties": merged,
            "required": required,
            "additionalProperties": False,
        }

    return ToolRegistry(
        [
            RegisteredTool(
                name="git_status",
                description="Return read-only git branch and dirty state metadata.",
                parameters=params({}, ["repo_name"]),
                func=partial(git_status, context),
            ),
            RegisteredTool(
                name="latest_commit",
                description="Return latest commit hash, date, and subject.",
                parameters=params({}, ["repo_name"]),
                func=partial(latest_commit, context),
            ),
            RegisteredTool(
                name="list_files",
                description=(
                    "List bounded public-safe file paths for a configured repo."
                ),
                parameters=params(
                    {
                        "patterns": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": None,
                        }
                    },
                    ["repo_name"],
                ),
                func=partial(list_files, context),
            ),
            RegisteredTool(
                name="read_safe_file",
                description="Read an approved small public-safe text file.",
                parameters=params(
                    {"relative_path": {"type": "string"}},
                    ["repo_name", "relative_path"],
                ),
                func=partial(read_safe_file, context),
            ),
            RegisteredTool(
                name="search_static_markers",
                description=(
                    "Search TODO, FIXME, and HACK markers in public-safe files."
                ),
                parameters=params({}, ["repo_name"]),
                func=partial(search_static_markers, context),
            ),
            RegisteredTool(
                name="summarize_source_tree",
                description=(
                    "Return bounded source tree metadata for source-code review."
                ),
                parameters=params({}, ["repo_name"]),
                func=partial(summarize_source_tree, context),
            ),
            RegisteredTool(
                name="list_source_files",
                description=(
                    "List bounded source files approved for semantic source review."
                ),
                parameters=params(
                    {
                        "patterns": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": None,
                        }
                    },
                    ["repo_name"],
                ),
                func=partial(list_source_files, context),
            ),
            RegisteredTool(
                name="read_source_file",
                description=(
                    "Read one bounded approved source-code file for review."
                ),
                parameters=params(
                    {"relative_path": {"type": "string"}},
                    ["repo_name", "relative_path"],
                ),
                func=partial(read_source_file, context),
            ),
            RegisteredTool(
                name="read_source_files",
                description=(
                    "Read a bounded batch of approved planned source-code files."
                ),
                parameters=params(
                    {
                        "relative_paths": {
                            "type": "array",
                            "items": {"type": "string"},
                        }
                    },
                    ["repo_name", "relative_paths"],
                ),
                func=partial(read_source_files, context),
            ),
            RegisteredTool(
                name="detect_dependency_manifests",
                description=(
                    "Detect dependency manifests without running package managers."
                ),
                parameters=params({}, ["repo_name"]),
                func=partial(detect_dependency_manifests, context),
            ),
            RegisteredTool(
                name="run_configured_safe_command",
                description=(
                    "Run an explicitly configured safe command with bounded "
                    "redacted output."
                ),
                parameters=params(
                    {"command_label": {"type": "string"}},
                    ["repo_name", "command_label"],
                ),
                func=partial(run_configured_safe_command, context),
            ),
        ]
    )
