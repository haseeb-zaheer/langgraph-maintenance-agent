"""Configuration loading and validation."""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)


class ConfigError(ValueError):
    """Raised when a maintenance agent config is invalid."""


class CheckName(StrEnum):
    """Supported configured check names."""

    GIT_STATUS = "git-status"
    DOCS = "docs"
    STATIC_SEARCH = "static-search"
    DEPENDENCY_METADATA = "dependency-metadata"
    TESTS = "tests"
    LINT = "lint"
    BUILD = "build"
    PYTHON_SYNTAX = "python-syntax"


UNSAFE_COMMAND_LABEL_RE = re.compile(
    r"(fix|format|upgrade|delete|remove|reset|checkout|commit|clean|migrate|install)",
    re.IGNORECASE,
)
UNSAFE_COMMAND_PATTERNS = (
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\brm\s+-rf\b",
        r"\bgit\s+reset\b",
        r"\bgit\s+checkout\b",
        r"\bgit\s+clean\b",
        r"\bnpm\s+audit\s+fix\b",
        r"\bpip\s+install\s+-U\b",
        r"\buv\s+add\b",
        r"\bpoetry\s+add\b",
        r"\balembic\s+upgrade\b",
    )
)
UNSAFE_COMMAND_PATTERN_LIST = tuple(UNSAFE_COMMAND_PATTERNS)


class SafeCommand(BaseModel):
    """A validated command explicitly allowed for a configured repository."""

    model_config = ConfigDict(frozen=True)

    label: str
    command: str

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("safe command label must not be empty")
        if UNSAFE_COMMAND_LABEL_RE.search(normalized):
            raise ValueError(f"unsafe safe command label: {value}")
        return normalized

    @field_validator("command")
    @classmethod
    def validate_command(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("safe command must not be empty")
        for pattern in UNSAFE_COMMAND_PATTERN_LIST:
            if pattern.search(normalized):
                raise ValueError(f"unsafe command string: {value}")
        return normalized


class RepoConfig(BaseModel):
    """Configuration for one allowlisted repository."""

    model_config = ConfigDict(extra="forbid")

    name: str
    path: Path | None = None
    enabled: bool
    checks: list[CheckName] = Field(default_factory=list)
    safe_commands: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int | None = None
    notes: str | None = None
    required: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("repo name must not be empty")
        return normalized

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("timeout_seconds must be positive")
        return value

    @field_validator("safe_commands")
    @classmethod
    def validate_safe_commands(cls, value: dict[str, str]) -> dict[str, str]:
        validated: dict[str, str] = {}
        for label, command in value.items():
            safe_command = SafeCommand(label=label, command=command)
            validated[safe_command.label] = safe_command.command
        return validated

    @model_validator(mode="after")
    def validate_enabled_repo(self) -> RepoConfig:
        if self.enabled and self.path is None:
            raise ValueError("enabled repo requires a path")
        return self

    def normalized_safe_commands(self) -> list[SafeCommand]:
        return [
            SafeCommand(label=label, command=command)
            for label, command in self.safe_commands.items()
        ]


class ReportSettings(BaseModel):
    """Local report and optional delivery settings."""

    model_config = ConfigDict(extra="forbid")

    output_dir: Path = Path("reports")
    filename_prefix: str = "routine-maintenance"
    update_latest: bool = True
    discord_enabled: bool = False

    @field_validator("filename_prefix")
    @classmethod
    def validate_filename_prefix(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("filename_prefix must not be empty")
        if "/" in normalized or "\\" in normalized:
            raise ValueError("filename_prefix must not contain path separators")
        return normalized


class AppConfig(BaseModel):
    """Top-level maintenance agent configuration."""

    model_config = ConfigDict(extra="forbid")

    repos: list[RepoConfig]
    report: ReportSettings = Field(default_factory=ReportSettings)

    @model_validator(mode="after")
    def validate_unique_repo_names(self) -> AppConfig:
        names = [repo.name for repo in self.repos]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            duplicate_list = ", ".join(duplicates)
            raise ValueError(f"duplicate repo names: {duplicate_list}")
        return self


def load_config(path: Path) -> AppConfig:
    """Load and validate a YAML maintenance config."""

    if not path.exists():
        raise ConfigError(f"config file does not exist: {path}")
    if not path.is_file():
        raise ConfigError(f"config path is not a file: {path}")

    try:
        raw_config: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in config file: {path}") from exc

    if raw_config is None:
        raise ConfigError(f"config file is empty: {path}")
    if not isinstance(raw_config, dict):
        raise ConfigError("config root must be a mapping")

    try:
        return AppConfig.model_validate(raw_config)
    except ValidationError as exc:
        raise ConfigError(str(exc)) from exc
