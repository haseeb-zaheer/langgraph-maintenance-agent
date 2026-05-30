"""Dependency manifest detection tools."""

from __future__ import annotations

from langgraph_maintenance_agent.tools.files import _iter_public_files
from langgraph_maintenance_agent.tools.registry import ToolContext
from langgraph_maintenance_agent.tools.results import (
    DependencyManifest,
    ToolError,
    ToolResult,
)

MANIFESTS = {
    "pyproject.toml": "python",
    "requirements.txt": "python",
    "requirements-dev.txt": "python",
    "uv.lock": "python",
    "poetry.lock": "python",
    "package.json": "node",
    "package-lock.json": "node",
    "pnpm-lock.yaml": "node",
    "yarn.lock": "node",
    "Dockerfile": "docker",
    "docker-compose.yml": "docker",
    "compose.yml": "docker",
    "dbt_project.yml": "dbt",
    "packages.yml": "dbt",
}


def detect_dependency_manifests(context: ToolContext, repo_name: str) -> ToolResult:
    """Identify dependency manifests without running package managers."""

    try:
        root = context.repo_root(repo_name)
    except KeyError as exc:
        return ToolResult(
            tool_name="detect_dependency_manifests",
            repo_name=repo_name,
            ok=False,
            error=ToolError(code="unknown_repo", message=str(exc)),
        )
    if not root.exists():
        return ToolResult(
            tool_name="detect_dependency_manifests",
            repo_name=repo_name,
            ok=False,
            error=ToolError(
                code="repo_path_missing", message="configured repo path does not exist"
            ),
        )
    manifests: list[DependencyManifest] = []
    for relative_path in _iter_public_files(root):
        ecosystem = MANIFESTS.get(relative_path.name)
        if ecosystem is not None:
            manifests.append(
                DependencyManifest(ecosystem=ecosystem, path=relative_path.as_posix())
            )
    return ToolResult(
        tool_name="detect_dependency_manifests",
        repo_name=repo_name,
        ok=True,
        data={"manifests": [manifest.model_dump() for manifest in manifests]},
    )
