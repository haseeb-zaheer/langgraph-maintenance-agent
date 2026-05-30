"""Repo-scoped safe tool registry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph_maintenance_agent.config import AppConfig, RepoConfig
from langgraph_maintenance_agent.tools.results import ToolLimits, ToolResult

ToolFunc = Callable[..., ToolResult]


@dataclass(frozen=True)
class ToolContext:
    """Validated repository allowlist and output limits for tools."""

    repos_by_name: dict[str, RepoConfig]
    limits: ToolLimits = ToolLimits()

    @classmethod
    def from_config(
        cls, config: AppConfig, limits: ToolLimits | None = None
    ) -> ToolContext:
        repos = {repo.name: repo for repo in config.repos if repo.enabled}
        return cls(repos_by_name=repos, limits=limits or ToolLimits())

    def repo_config(self, repo_name: str) -> RepoConfig:
        try:
            return self.repos_by_name[repo_name]
        except KeyError as exc:
            raise KeyError(f"unknown or disabled repo: {repo_name}") from exc

    def repo_root(self, repo_name: str) -> Path:
        repo = self.repo_config(repo_name)
        if repo.path is None:
            raise KeyError(f"repo has no configured path: {repo_name}")
        return repo.path.expanduser().resolve()


@dataclass(frozen=True)
class RegisteredTool:
    """A callable tool plus OpenAI/OpenRouter-compatible schema."""

    name: str
    description: str
    parameters: dict[str, Any]
    func: ToolFunc

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Registry that exposes only configured safe tools."""

    def __init__(self, tools: list[RegisteredTool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def names(self) -> list[str]:
        return sorted(self._tools)

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.openai_schema() for tool in self._tools.values()]

    def get(self, name: str) -> RegisteredTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"unregistered tool: {name}") from exc

    def call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        return self.get(name).func(**arguments)


def repo_name_parameter(repo_names: list[str]) -> dict[str, Any]:
    """Return the common repo_name parameter schema."""

    return {"type": "string", "enum": repo_names}
