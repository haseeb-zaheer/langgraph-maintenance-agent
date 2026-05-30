"""Read-only safe filesystem tools."""

from __future__ import annotations

import fnmatch
from collections.abc import Iterator
from pathlib import Path

from langgraph_maintenance_agent.runtime.text import bound_text
from langgraph_maintenance_agent.tools.registry import ToolContext
from langgraph_maintenance_agent.tools.results import FileEntry, ToolError, ToolResult
from langgraph_maintenance_agent.tools.safety import (
    UnsafePathError,
    assert_safe_read_path,
    contains_nul_bytes,
    is_binary_path,
    is_blocked_relative_path,
    is_sensitive_path_part,
    read_text_excerpt,
    redact_sensitive_lines,
    resolve_inside_repo,
)


def _iter_public_files(root: Path) -> list[Path]:
    paths: list[Path] = []
    for path in _walk_public_file_paths(root):
        rel = path.relative_to(root)
        paths.append(rel)
    return sorted(paths, key=lambda item: item.as_posix())


def _walk_public_file_paths(root: Path) -> Iterator[Path]:
    for path in root.iterdir():
        if path.is_symlink() or is_sensitive_path_part(path.name):
            continue
        rel = path.relative_to(root)
        if is_blocked_relative_path(rel):
            continue
        if path.is_dir():
            yield from _walk_public_file_paths(path)
            continue
        if not path.is_file():
            continue
        if is_blocked_relative_path(rel) or is_binary_path(rel):
            continue
        try:
            resolve_inside_repo(root, path)
        except UnsafePathError:
            continue
        yield path


def list_files(
    context: ToolContext,
    repo_name: str,
    patterns: list[str] | None = None,
) -> ToolResult:
    """List bounded public-safe repository file paths."""

    try:
        root = context.repo_root(repo_name)
    except KeyError as exc:
        return ToolResult(
            tool_name="list_files",
            repo_name=repo_name,
            ok=False,
            error=ToolError(code="unknown_repo", message=str(exc)),
        )
    if not root.exists():
        return ToolResult(
            tool_name="list_files",
            repo_name=repo_name,
            ok=False,
            error=ToolError(
                code="repo_path_missing", message="configured repo path does not exist"
            ),
        )
    files = _iter_public_files(root)
    if patterns:
        files = [
            path
            for path in files
            if any(fnmatch.fnmatch(path.as_posix(), pattern) for pattern in patterns)
        ]
    truncated = len(files) > context.limits.max_files
    entries = [
        FileEntry(
            path=path.as_posix(), size_bytes=(root / path).stat().st_size
        ).model_dump()
        for path in files[: context.limits.max_files]
    ]
    return ToolResult(
        tool_name="list_files",
        repo_name=repo_name,
        ok=True,
        data={"files": entries, "truncated": truncated},
    )


def read_safe_file(
    context: ToolContext, repo_name: str, relative_path: str
) -> ToolResult:
    """Read one approved safe text file from a configured repository."""

    try:
        root = context.repo_root(repo_name)
        path = assert_safe_read_path(
            root, relative_path, context.limits.max_bytes_per_file
        )
        if contains_nul_bytes(path):
            raise UnsafePathError("binary files are not readable")
        raw_text, truncated = read_text_excerpt(
            path, context.limits.max_bytes_per_file
        )
    except (OSError, UnicodeError, UnsafePathError, KeyError) as exc:
        return ToolResult(
            tool_name="read_safe_file",
            repo_name=repo_name,
            ok=False,
            error=ToolError(code="safe_read_rejected", message=str(exc)),
        )
    text = redact_sensitive_lines(raw_text)
    return ToolResult(
        tool_name="read_safe_file",
        repo_name=repo_name,
        ok=True,
        data={
            "path": Path(relative_path).as_posix(),
            "content": bound_text(text, context.limits.max_bytes_per_file),
            "truncated": truncated,
        },
    )
