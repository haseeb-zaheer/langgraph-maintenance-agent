"""Shared domain schemas for the maintenance agent."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Literal

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
    BUG_RISK = "bug-risk"
    REFACTOR = "refactor"
    CODE_QUALITY = "code-quality"
    TEST_GAP = "test-gap"


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
    timeout_seconds: int | None = None


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


class ToolCallSummary(BaseModel):
    """Bounded metadata for one repo inspector tool call."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    status: str
    argument_keys: list[str] = Field(default_factory=list)
    error_code: str | None = None


class SourceReviewTarget(BaseModel):
    """One source file selected for staged LLM review."""

    model_config = ConfigDict(extra="forbid")

    path: str
    reason: str


class SourceReviewPlan(BaseModel):
    """Validated LLM source-review plan produced before source reads."""

    model_config = ConfigDict(extra="forbid")

    repo_name: str
    rationale: str
    targets: list[SourceReviewTarget] = Field(default_factory=list)


class SourceFileMetadata(BaseModel):
    """Public-safe source file candidate metadata."""

    model_config = ConfigDict(extra="forbid")

    path: str
    size_bytes: int
    language: str
    signals: list[str] = Field(default_factory=list)
    priority: int = 0
    nearby_test: bool = False


class ReadSourceFileMetadata(BaseModel):
    """Metadata for a source file actually read for review."""

    model_config = ConfigDict(extra="forbid")

    path: str
    size_bytes: int
    bytes_read: int
    truncated: bool = False


class SkippedSourceFileMetadata(BaseModel):
    """Metadata for a planned source file that was skipped."""

    model_config = ConfigDict(extra="forbid")

    path: str
    reason: str


class SourceReviewCoverage(BaseModel):
    """Coverage summary for one staged source-review run."""

    model_config = ConfigDict(extra="forbid")

    candidate_files: int = 0
    planned_files: int = 0
    read_files: int = 0
    bytes_read: int = 0
    skipped_files: int = 0
    generated_files_skipped: int = 0
    review_mode: str = "not-run"
    validation_status: str = "not-run"
    validation_error: str | None = None
    repair_attempted: bool = False
    plan_rationale: str | None = None
    planned: list[SourceReviewTarget] = Field(default_factory=list)
    candidates: list[SourceFileMetadata] = Field(default_factory=list)
    read: list[ReadSourceFileMetadata] = Field(default_factory=list)
    skipped: list[SkippedSourceFileMetadata] = Field(default_factory=list)


class RepoInspectionMetadata(BaseModel):
    """Public-safe metadata for one repo inspector branch."""

    model_config = ConfigDict(extra="forbid")

    tool_calls: list[ToolCallSummary] = Field(default_factory=list)
    tool_calls_made: int = 0
    iterations: int = 0
    model_provider: str | None = None
    model_name: str | None = None
    source_review: SourceReviewCoverage | None = None


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
    metadata: RepoInspectionMetadata = Field(default_factory=RepoInspectionMetadata)


class RepoInspectorOutput(BaseModel):
    """Structured final output from a repository inspector agent."""

    model_config = ConfigDict(extra="forbid")

    repo_name: str
    summary: str
    findings: list[Finding] = Field(default_factory=list)
    skipped_checks: list[SkippedCheck] = Field(default_factory=list)
    command_results: list[CommandResult] = Field(default_factory=list)
    errors: list[AgentError] = Field(default_factory=list)


SourceReviewFindingCategory = Literal[
    FindingCategory.BUG_RISK,
    FindingCategory.REFACTOR,
    FindingCategory.CODE_QUALITY,
    FindingCategory.TEST_GAP,
]


class SourceReviewFinding(BaseModel):
    """Strict source-review finding returned by the staged source-review call."""

    model_config = ConfigDict(extra="forbid")

    repo_name: str
    severity: Severity
    category: SourceReviewFindingCategory
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    evidence_paths: list[str] = Field(min_length=1)
    suggested_action: str = Field(min_length=1)
    needs_human_review: bool = False

    def to_finding(self) -> Finding:
        """Convert a strict source-review finding to the normalized schema."""

        return Finding(
            repo_name=self.repo_name,
            severity=self.severity,
            category=self.category,
            title=self.title,
            description=self.description,
            evidence_paths=self.evidence_paths,
            suggested_action=self.suggested_action,
            needs_human_review=self.needs_human_review,
        )


class SourceReviewOutput(BaseModel):
    """Structured final output from the staged source-review agent call."""

    model_config = ConfigDict(extra="forbid")

    repo_name: str
    summary: str
    findings: list[SourceReviewFinding] = Field(default_factory=list)
    skipped_checks: list[SkippedCheck] = Field(default_factory=list)
    errors: list[AgentError] = Field(default_factory=list)


class SummaryOutput(BaseModel):
    """Structured cross-repository summary output."""

    model_config = ConfigDict(extra="forbid")

    executive_summary: str
    next_actions: list[str] = Field(default_factory=list)


class IncompleteAgentRun(BaseModel):
    """Structured marker for an incomplete agent run."""

    model_config = ConfigDict(extra="forbid")

    repo_name: str
    reason: str
    stage: str
    tool_calls_made: int = 0
    iterations: int = 0


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
