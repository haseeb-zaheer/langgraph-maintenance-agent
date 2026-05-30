"""JSON-serializable safe tool result schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolLimits(BaseModel):
    """Bounds applied to repository tool outputs."""

    model_config = ConfigDict(frozen=True)

    max_files: int = 200
    max_bytes_per_file: int = 16_384
    max_search_matches: int = 50
    max_output_chars: int = 12_000


class ToolError(BaseModel):
    """Structured tool error safe to pass to an LLM."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class ToolResult(BaseModel):
    """Common envelope returned by all safe tools."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    repo_name: str
    ok: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: ToolError | None = None


class FileEntry(BaseModel):
    """A safe repository file path."""

    model_config = ConfigDict(extra="forbid")

    path: str
    size_bytes: int | None = None


class SearchMatch(BaseModel):
    """A bounded public-safe static marker match."""

    model_config = ConfigDict(extra="forbid")

    path: str
    line_number: int
    marker: str
    line_excerpt: str


class DependencyManifest(BaseModel):
    """Detected dependency manifest metadata."""

    model_config = ConfigDict(extra="forbid")

    ecosystem: str
    path: str


ToolCallStatus = Literal["completed", "failed", "skipped"]


class ToolCallRecord(BaseModel):
    """A record of one agent-requested tool call."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    repo_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: ToolCallStatus
    result: ToolResult | None = None
    error: str | None = None
