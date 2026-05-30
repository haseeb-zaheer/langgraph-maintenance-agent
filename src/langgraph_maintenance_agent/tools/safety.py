"""Safety checks for read-only repository tools."""

from __future__ import annotations

import mimetypes
import re
from collections.abc import Iterator
from pathlib import Path

SENSITIVE_NAMES = {
    ".env",
    ".env.local",
    ".envrc",
    "id_rsa",
    "id_dsa",
    "id_ed25519",
    "known_hosts",
}
SENSITIVE_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".log",
}
SENSITIVE_PARTS = {
    ".git",
    ".hg",
    ".svn",
    ".cache",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    "reports",
}
SAFE_READ_NAMES = {
    "README",
    "README.md",
    "ARCHITECTURE.md",
    "PRD.md",
    "AGENTS.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "pyproject.toml",
    "uv.lock",
    "requirements.txt",
    "requirements-dev.txt",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "Dockerfile",
    "docker-compose.yml",
    "compose.yml",
    "dbt_project.yml",
    "packages.yml",
}
SAFE_READ_SUFFIXES = {".md", ".rst", ".txt", ".toml", ".yaml", ".yml", ".json"}
TEXTUAL_SUFFIXES = SAFE_READ_SUFFIXES | {".py", ".js", ".ts", ".tsx", ".jsx", ".css"}
BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".pdf",
    ".zip",
    ".gz",
    ".tar",
    ".7z",
    ".bin",
    ".so",
    ".dll",
    ".dylib",
    ".pyc",
}
SECRET_LINE_RE = re.compile(
    r"(api[_-]?key|token|secret|password|authorization:\s*bearer|BEGIN .*PRIVATE KEY)",
    re.IGNORECASE,
)


class UnsafePathError(ValueError):
    """Raised when a tool path is outside the public-safe boundary."""


def normalize_relative_path(relative_path: str) -> Path:
    """Return a normalized relative path or raise for traversal/absolute input."""

    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise UnsafePathError("absolute paths are not allowed")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise UnsafePathError("path traversal is not allowed")
    return candidate


def is_sensitive_relative_path(path: Path) -> bool:
    """Return whether a relative path should be excluded from tool output."""

    parts = set(path.parts)
    name = path.name
    lower_name = name.lower()
    return (
        lower_name in SENSITIVE_NAMES
        or path.suffix.lower() in SENSITIVE_SUFFIXES
        or bool(parts & SENSITIVE_PARTS)
        or lower_name.endswith(".env")
        or "private" in lower_name
        and path.suffix.lower() in {".key", ".pem"}
    )


def is_sensitive_path_part(name: str) -> bool:
    """Return whether a single path component is blocked from traversal."""

    lower_name = name.lower()
    return lower_name in SENSITIVE_NAMES or lower_name in SENSITIVE_PARTS


def is_binary_path(path: Path) -> bool:
    """Return whether a path is likely binary based on extension/MIME."""

    if path.suffix.lower() in TEXTUAL_SUFFIXES or path.name == "Dockerfile":
        return False
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    mime_type, _ = mimetypes.guess_type(path.name)
    return bool(
        mime_type and not mime_type.startswith("text/") and "json" not in mime_type
    )


def resolve_inside_repo(repo_root: Path, path: Path) -> Path:
    """Resolve a path and require it to stay under the repository root."""

    resolved_root = repo_root.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise UnsafePathError("path escapes repository root") from exc
    return resolved


def assert_safe_read_path(repo_root: Path, relative_path: str, max_bytes: int) -> Path:
    """Validate and resolve a safe file read path inside a repository."""

    normalized = normalize_relative_path(relative_path)
    if is_sensitive_relative_path(normalized):
        raise UnsafePathError("path is blocked by sensitive path rules")
    if is_binary_path(normalized):
        raise UnsafePathError("binary files are not readable")
    if (
        normalized.name not in SAFE_READ_NAMES
        and normalized.suffix not in SAFE_READ_SUFFIXES
    ):
        raise UnsafePathError("file type is not approved for safe reads")

    candidate = repo_root / normalized
    if candidate.is_symlink():
        raise UnsafePathError("symlinked files are not readable")
    resolved = resolve_inside_repo(repo_root, candidate)
    if not resolved.is_file():
        raise UnsafePathError("path is not a file")
    if resolved.stat().st_size > max_bytes:
        raise UnsafePathError("file exceeds safe read size limit")
    return resolved


def contains_nul_bytes(path: Path, sample_size: int = 2048) -> bool:
    """Return whether a file sample contains NUL bytes."""

    with path.open("rb") as handle:
        return b"\x00" in handle.read(sample_size)


def read_text_excerpt(path: Path, max_bytes: int) -> tuple[str, bool]:
    """Read at most max_bytes from a text file and report truncation."""

    with path.open("rb") as handle:
        data = handle.read(max_bytes + 1)
    truncated = len(data) > max_bytes
    return data[:max_bytes].decode("utf-8", errors="replace"), truncated


def iter_text_lines(path: Path, max_bytes: int) -> Iterator[tuple[int, str]]:
    """Yield decoded lines from at most max_bytes of a file."""

    text, _ = read_text_excerpt(path, max_bytes)
    yield from enumerate(text.splitlines(), start=1)


def redact_sensitive_lines(text: str) -> str:
    """Replace lines that look like secrets with redaction markers."""

    redacted: list[str] = []
    for line in text.splitlines():
        if SECRET_LINE_RE.search(line):
            redacted.append("[redacted sensitive line]")
        else:
            redacted.append(line)
    return "\n".join(redacted)
