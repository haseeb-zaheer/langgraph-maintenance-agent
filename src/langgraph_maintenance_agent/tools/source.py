"""Bounded source-code review tools."""

from __future__ import annotations

import fnmatch
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

from langgraph_maintenance_agent.config import RepoConfig
from langgraph_maintenance_agent.runtime.text import bound_text
from langgraph_maintenance_agent.tools.registry import ToolContext
from langgraph_maintenance_agent.tools.results import FileEntry, ToolError, ToolResult
from langgraph_maintenance_agent.tools.safety import (
    UnsafePathError,
    contains_nul_bytes,
    is_binary_path,
    is_blocked_relative_path,
    is_sensitive_path_part,
    normalize_relative_path,
    read_text_excerpt,
    redact_sensitive_lines,
    resolve_inside_repo,
)

SOURCE_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".css",
    ".scss",
}
DEFAULT_SOURCE_PATTERNS = [
    "*.py",
    "*.js",
    "*.jsx",
    "*.mjs",
    "*.cjs",
    "*.ts",
    "*.tsx",
    "*.css",
    "*.scss",
]
DEFAULT_SOURCE_ROOT_CANDIDATES = [
    "src",
    "app",
    "pages",
    "components",
    "lib",
    "tests",
    "test",
]


def summarize_source_tree(context: ToolContext, repo_name: str) -> ToolResult:
    """Return bounded source tree metadata for a configured repository."""

    resolved = _resolve_repo(context, repo_name, "summarize_source_tree")
    if isinstance(resolved, ToolResult):
        return resolved
    repo, root = resolved
    source_files = _source_files(root, repo)
    limited_files, total_bytes, truncated = _apply_source_budget(
        root, repo, source_files
    )
    suffix_counts = Counter(path.suffix.lower() or "[none]" for path in source_files)
    source_roots = [path.as_posix() for path in _source_roots(root, repo)]
    test_roots = [
        item
        for item in source_roots
        if item in {"test", "tests"}
        or item.endswith("/test")
        or item.endswith("/tests")
    ]
    return ToolResult(
        tool_name="summarize_source_tree",
        repo_name=repo_name,
        ok=True,
        data={
            "source_roots": source_roots,
            "test_roots": test_roots,
            "languages": _language_counts(suffix_counts),
            "framework_signals": _framework_signals(root),
            "candidate_files": [
                FileEntry(path=path.as_posix(), size_bytes=(root / path).stat().st_size)
                .model_dump()
                for path in limited_files
            ],
            "total_source_files": len(source_files),
            "budgeted_source_files": len(limited_files),
            "budgeted_bytes": total_bytes,
            "truncated": truncated,
        },
    )


def list_source_files(
    context: ToolContext,
    repo_name: str,
    patterns: list[str] | None = None,
) -> ToolResult:
    """List bounded source-code files approved for source review."""

    resolved = _resolve_repo(context, repo_name, "list_source_files")
    if isinstance(resolved, ToolResult):
        return resolved
    repo, root = resolved
    files = _source_files(root, repo)
    if patterns:
        files = [
            path
            for path in files
            if any(fnmatch.fnmatch(path.as_posix(), pattern) for pattern in patterns)
        ]
    limited_files, total_bytes, truncated = _apply_source_budget(root, repo, files)
    entries = [
        FileEntry(path=path.as_posix(), size_bytes=(root / path).stat().st_size)
        .model_dump()
        for path in limited_files
    ]
    return ToolResult(
        tool_name="list_source_files",
        repo_name=repo_name,
        ok=True,
        data={
            "files": entries,
            "total_matching_files": len(files),
            "budgeted_bytes": total_bytes,
            "truncated": truncated,
        },
    )


def read_source_file(
    context: ToolContext,
    repo_name: str,
    relative_path: str,
) -> ToolResult:
    """Read one bounded source-code file from a configured repository."""

    try:
        repo = context.repo_config(repo_name)
        root = context.repo_root(repo_name)
        path = _assert_safe_source_path(root, repo, relative_path)
        raw_text, truncated = read_text_excerpt(
            path,
            repo.source_review_max_bytes_per_file,
        )
    except (OSError, UnicodeError, UnsafePathError, KeyError) as exc:
        return ToolResult(
            tool_name="read_source_file",
            repo_name=repo_name,
            ok=False,
            error=ToolError(code="source_read_rejected", message=str(exc)),
        )
    text = redact_sensitive_lines(raw_text)
    return ToolResult(
        tool_name="read_source_file",
        repo_name=repo_name,
        ok=True,
        data={
            "path": Path(relative_path).as_posix(),
            "content": bound_text(text, repo.source_review_max_bytes_per_file),
            "truncated": truncated,
            "bytes_read": min(
                path.stat().st_size,
                repo.source_review_max_bytes_per_file,
            ),
        },
    )


def _resolve_repo(
    context: ToolContext,
    repo_name: str,
    tool_name: str,
) -> tuple[RepoConfig, Path] | ToolResult:
    try:
        repo = context.repo_config(repo_name)
        root = context.repo_root(repo_name)
    except KeyError as exc:
        return ToolResult(
            tool_name=tool_name,
            repo_name=repo_name,
            ok=False,
            error=ToolError(code="unknown_repo", message=str(exc)),
        )
    if not root.exists():
        return ToolResult(
            tool_name=tool_name,
            repo_name=repo_name,
            ok=False,
            error=ToolError(
                code="repo_path_missing",
                message="configured repo path does not exist",
            ),
        )
    return repo, root


def _source_roots(root: Path, repo: RepoConfig) -> list[Path]:
    if repo.source_roots:
        return [Path(item) for item in repo.source_roots]
    roots = [
        Path(candidate)
        for candidate in DEFAULT_SOURCE_ROOT_CANDIDATES
        if (root / candidate).is_dir()
    ]
    if roots:
        return roots
    if any(path.suffix.lower() == ".py" for path in root.iterdir() if path.is_file()):
        return [Path(".")]
    return [Path(".")]


def _source_files(root: Path, repo: RepoConfig) -> list[Path]:
    patterns = repo.source_include_patterns or DEFAULT_SOURCE_PATTERNS
    files: list[Path] = []
    for source_root in _source_roots(root, repo):
        absolute_root = root / source_root
        if source_root != Path(".") and not absolute_root.is_dir():
            continue
        for path in _walk_source_paths(absolute_root, root):
            rel = path.relative_to(root)
            rel_text = rel.as_posix()
            if not any(fnmatch.fnmatch(rel_text, pattern) for pattern in patterns):
                continue
            if any(
                fnmatch.fnmatch(rel_text, pattern)
                for pattern in repo.source_exclude_patterns
            ):
                continue
            if path.stat().st_size > repo.source_review_max_bytes_per_file:
                continue
            files.append(rel)
    return sorted(set(files), key=lambda item: item.as_posix())


def _walk_source_paths(path: Path, root: Path) -> Iterator[Path]:
    if path.is_symlink():
        return
    if path.is_dir():
        for child in path.iterdir():
            if child.is_symlink() or is_sensitive_path_part(child.name):
                continue
            rel = child.relative_to(root)
            if is_blocked_relative_path(rel):
                continue
            yield from _walk_source_paths(child, root)
        return
    if not path.is_file():
        return
    rel = path.relative_to(root)
    if (
        is_blocked_relative_path(rel)
        or is_binary_path(rel)
        or path.suffix.lower() not in SOURCE_SUFFIXES
    ):
        return
    try:
        resolve_inside_repo(root, path)
    except UnsafePathError:
        return
    yield path


def _apply_source_budget(
    root: Path,
    repo: RepoConfig,
    files: list[Path],
) -> tuple[list[Path], int, bool]:
    limited: list[Path] = []
    total_bytes = 0
    for path in files:
        size = (root / path).stat().st_size
        if len(limited) >= repo.source_review_max_files:
            return limited, total_bytes, True
        if total_bytes + size > repo.source_review_max_total_bytes:
            return limited, total_bytes, True
        limited.append(path)
        total_bytes += size
    return limited, total_bytes, len(limited) < len(files)


def _assert_safe_source_path(root: Path, repo: RepoConfig, relative_path: str) -> Path:
    normalized = normalize_relative_path(relative_path)
    if is_blocked_relative_path(normalized):
        raise UnsafePathError("path is blocked by sensitive or generated path rules")
    if normalized.suffix.lower() not in SOURCE_SUFFIXES:
        raise UnsafePathError("file type is not approved for source reads")
    source_files = set(_source_files(root, repo))
    if normalized not in source_files:
        raise UnsafePathError("path is not within approved source review scope")
    candidate = root / normalized
    if candidate.is_symlink():
        raise UnsafePathError("symlinked files are not readable")
    resolved = resolve_inside_repo(root, candidate)
    if not resolved.is_file():
        raise UnsafePathError("path is not a file")
    if contains_nul_bytes(resolved):
        raise UnsafePathError("binary files are not readable")
    if resolved.stat().st_size > repo.source_review_max_bytes_per_file:
        raise UnsafePathError("file exceeds source read size limit")
    return resolved


def _language_counts(suffix_counts: Counter[str]) -> dict[str, int]:
    mapping = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".mjs": "javascript",
        ".cjs": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".css": "css",
        ".scss": "css",
    }
    counts: dict[str, int] = {}
    for suffix, count in suffix_counts.items():
        language = mapping.get(suffix)
        if language is not None:
            counts[language] = counts.get(language, 0) + count
    return counts


def _framework_signals(root: Path) -> list[str]:
    signals: list[str] = []
    package_json = root / "package.json"
    pyproject = root / "pyproject.toml"
    if package_json.is_file():
        signals.append("node")
        try:
            package_text = package_json.read_text(encoding="utf-8", errors="replace")
        except OSError:
            package_text = ""
        if '"next"' in package_text:
            signals.append("nextjs")
        if '"react"' in package_text:
            signals.append("react")
    if pyproject.is_file() or any(root.glob("*.py")):
        signals.append("python")
    return sorted(set(signals))
