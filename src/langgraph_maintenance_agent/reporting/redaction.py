"""Report redaction helpers."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

REDACTION_MARKER = "[redacted]"

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "discord_webhook_url",
        re.compile(
            r"https://(?:canary\.)?discord\.com/api/webhooks/\S+", re.IGNORECASE
        ),
    ),
    ("api_key", re.compile(r"\bsk-(?:or-|proj-)?[A-Za-z0-9_-]{12,}\b")),
    ("github_token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{12,}\b")),
    ("github_token", re.compile(r"\b" + "ghp" + r"_[A-Za-z0-9_]{12,}\b")),
    (
        "authorization_header",
        re.compile(r"authorization:\s*bearer\s+\S+", re.IGNORECASE),
    ),
    (
        "secret_line",
        re.compile(r"(?im)^(.*(?:api[_-]?key|token|secret|password).*)$"),
    ),
    (
        "private_key",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----"
            r"[\s\S]*?"
            r"-----END [A-Z ]*PRIVATE KEY-----",
            re.IGNORECASE,
        ),
    ),
    (
        "private_key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.IGNORECASE),
    ),
)


@dataclass(frozen=True)
class RedactionResult:
    """Redacted text plus non-sensitive match metadata."""

    text: str
    total_count: int
    counts_by_type: dict[str, int]


def redact_text_with_metadata(text: str) -> RedactionResult:
    """Redact common secret-like values and return aggregate metadata."""

    redacted = text
    counts: Counter[str] = Counter()
    for secret_type, pattern in SECRET_PATTERNS:
        redacted, count = pattern.subn(REDACTION_MARKER, redacted)
        if count:
            counts[secret_type] += count
    return RedactionResult(
        text=redacted,
        total_count=sum(counts.values()),
        counts_by_type=dict(counts),
    )


def redact_text(text: str) -> str:
    """Redact common secret-like values from report text."""

    return redact_text_with_metadata(text).text
