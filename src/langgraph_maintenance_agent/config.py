"""Configuration loading and validation."""

from __future__ import annotations

import shlex
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
    SOURCE_REVIEW = "source-review"
    BUG_RISK_REVIEW = "bug-risk-review"
    REFACTOR_REVIEW = "refactor-review"
    TEST_GAP_REVIEW = "test-gap-review"


COMMAND_CHECK_LABELS: dict[CheckName, str] = {
    CheckName.TESTS: "tests",
    CheckName.LINT: "lint",
    CheckName.BUILD: "build",
    CheckName.PYTHON_SYNTAX: "python-syntax",
}

COMMAND_LABELS = frozenset(COMMAND_CHECK_LABELS.values())
PYTHON_EXECUTABLE_NAMES = frozenset({"python", "python3", "python3.11", "python3.12"})
DISALLOWED_RUFF_CHECK_FLAGS = frozenset(
    {"--fix", "--unsafe-fixes", "--fix-only", "--add-noqa"}
)


class SafeCommandPolicyError(ValueError):
    """Raised when a configured command is outside the report-only profile."""


def allowed_command_labels(checks: list[CheckName]) -> set[str]:
    """Return command labels enabled by configured checks."""

    return {
        label
        for check, label in COMMAND_CHECK_LABELS.items()
        if check in checks
    }


def parse_safe_command(command: str) -> list[str]:
    """Parse a configured command into argv."""

    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise SafeCommandPolicyError(str(exc)) from exc
    if not argv:
        raise SafeCommandPolicyError("safe command must not be empty")
    return argv


def executable_name(argv: list[str]) -> str:
    """Return the lowercase basename for argv[0]."""

    return Path(argv[0]).name.lower()


def is_python_executable(argv: list[str]) -> bool:
    """Return whether argv[0] looks like a Python executable."""

    name = executable_name(argv)
    return name in PYTHON_EXECUTABLE_NAMES or name.startswith("python3.")


def validate_safe_command_profile(label: str, command: str) -> list[str]:
    """Validate a configured command against narrow diagnostic profiles."""

    normalized_label = label.strip()
    if normalized_label not in COMMAND_LABELS:
        raise SafeCommandPolicyError(
            f"unsupported safe command label: {normalized_label}"
        )
    argv = parse_safe_command(command)
    if normalized_label == "tests":
        if executable_name(argv) == "pytest" or (
            len(argv) >= 3
            and is_python_executable(argv)
            and argv[1:3] == ["-m", "pytest"]
        ):
            return argv
    elif normalized_label == "lint":
        if executable_name(argv) == "ruff" and len(argv) >= 2 and argv[1] == "check":
            if DISALLOWED_RUFF_CHECK_FLAGS & set(argv[2:]):
                raise SafeCommandPolicyError("ruff check fix flags are not allowed")
            return argv
    elif normalized_label == "python-syntax":
        if len(argv) >= 3 and is_python_executable(argv) and argv[1] == "-m":
            if argv[2] in {"compileall", "py_compile"}:
                return argv
    elif normalized_label == "build":
        if len(argv) >= 3 and is_python_executable(argv) and argv[1:3] == [
            "-m",
            "build",
        ]:
            return argv
    raise SafeCommandPolicyError(
        f"safe command `{normalized_label}` must match an approved diagnostic profile"
    )


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
        if normalized not in COMMAND_LABELS:
            raise ValueError(f"unsupported safe command label: {value}")
        return normalized

    @field_validator("command")
    @classmethod
    def validate_command(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("safe command must not be empty")
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
    source_roots: list[str] = Field(default_factory=list)
    source_include_patterns: list[str] = Field(default_factory=list)
    source_exclude_patterns: list[str] = Field(default_factory=list)
    source_review_max_files: int = 20
    source_review_max_plan_files: int = 12
    source_review_max_bytes_per_file: int = 12_000
    source_review_max_total_bytes: int = 80_000
    source_review_max_snippets: int = 8

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

    @field_validator(
        "source_review_max_files",
        "source_review_max_plan_files",
        "source_review_max_bytes_per_file",
        "source_review_max_total_bytes",
        "source_review_max_snippets",
    )
    @classmethod
    def validate_positive_source_budget(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("source review budgets must be positive")
        return value

    @field_validator(
        "source_roots",
        "source_include_patterns",
        "source_exclude_patterns",
    )
    @classmethod
    def validate_source_path_values(cls, value: list[str]) -> list[str]:
        validated: list[str] = []
        for item in value:
            normalized = item.strip()
            if not normalized:
                raise ValueError("source path values must not be empty")
            path = Path(normalized)
            if path.is_absolute():
                raise ValueError("source path values must be relative")
            if any(part in {"", ".."} for part in path.parts):
                raise ValueError("source path values must not use traversal")
            validated.append(path.as_posix())
        return validated

    @field_validator("safe_commands")
    @classmethod
    def validate_safe_commands(cls, value: dict[str, str]) -> dict[str, str]:
        validated: dict[str, str] = {}
        for label, command in value.items():
            safe_command = SafeCommand(label=label, command=command)
            try:
                validate_safe_command_profile(
                    safe_command.label, safe_command.command
                )
            except SafeCommandPolicyError as exc:
                raise ValueError(str(exc)) from exc
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


def _resolve_relative_repo_paths(raw_config: dict[str, Any], config_path: Path) -> None:
    """Resolve relative repo paths against the config file location in-place."""

    repos = raw_config.get("repos")
    if not isinstance(repos, list):
        return

    config_dir = config_path.expanduser().resolve().parent
    for repo in repos:
        if not isinstance(repo, dict) or "path" not in repo:
            continue
        raw_path = repo["path"]
        if not isinstance(raw_path, str):
            continue
        expanded_path = Path(raw_path).expanduser()
        if expanded_path.is_absolute():
            continue
        repo["path"] = str((config_dir / expanded_path).resolve())


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

    _resolve_relative_repo_paths(raw_config, path)

    try:
        return AppConfig.model_validate(raw_config)
    except ValidationError as exc:
        raise ConfigError(str(exc)) from exc
