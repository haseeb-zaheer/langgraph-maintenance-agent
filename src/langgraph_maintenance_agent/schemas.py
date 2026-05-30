"""Shared domain schemas for the maintenance agent."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Severity(StrEnum):
    """Finding severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class FindingCategory(StrEnum):
    """Finding categories used for grouping and reporting."""

    SECURITY = "security"
    DEPENDENCY = "dependency"
    TEST = "test"
    BUILD = "build"
    GIT = "git"
    DOCS = "docs"
    STATIC = "static"
    RUNTIME = "runtime"
    CONFIGURATION = "configuration"


class Finding(BaseModel):
    """A normalized maintenance finding."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    repo_name: str
    severity: Severity
    category: FindingCategory
    title: str
    description: str
    evidence_paths: list[str] = Field(default_factory=list)
    command_label: str | None = None
    suggested_action: str | None = None
    needs_human_review: bool = False

    @model_validator(mode="after")
    def populate_id(self) -> Finding:
        if self.id is None:
            self.id = finding_fingerprint(self)
        return self


class CommandResult(BaseModel):
    """A bounded summary of a configured command execution."""

    model_config = ConfigDict(extra="forbid")

    label: str
    command: str | list[str]
    working_directory: str
    exit_code: int | None = None
    timed_out: bool = False
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""
    duration_seconds: float | None = None


class SkippedCheck(BaseModel):
    """A check that was intentionally not run."""

    model_config = ConfigDict(extra="forbid")

    repo_name: str
    check_name: str
    reason: str


class AgentError(BaseModel):
    """A fatal or partial workflow error."""

    model_config = ConfigDict(extra="forbid")

    message: str
    repo_name: str | None = None
    stage: str | None = None
    recoverable: bool = True


class RepoResult(BaseModel):
    """All structured results for one configured repository."""

    model_config = ConfigDict(extra="forbid")

    repo_name: str
    path: str | None = None
    enabled: bool = True
    findings: list[Finding] = Field(default_factory=list)
    skipped_checks: list[SkippedCheck] = Field(default_factory=list)
    command_results: list[CommandResult] = Field(default_factory=list)
    errors: list[AgentError] = Field(default_factory=list)


class DeliveryStatus(BaseModel):
    """Report delivery status for optional destinations."""

    model_config = ConfigDict(extra="forbid")

    destination: str
    attempted: bool = False
    success: bool = False
    message: str | None = None


def finding_fingerprint(finding: Finding) -> str:
    """Return a stable fingerprint for a finding, excluding its existing id."""

    payload = {
        "repo_name": finding.repo_name,
        "severity": finding.severity.value,
        "category": finding.category.value,
        "title": finding.title,
        "description": finding.description,
        "evidence_paths": sorted(finding.evidence_paths),
        "command_label": finding.command_label,
        "suggested_action": finding.suggested_action,
        "needs_human_review": finding.needs_human_review,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
