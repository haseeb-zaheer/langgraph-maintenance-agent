"""Minimum report redaction before local persistence."""

from __future__ import annotations

import re

REDACTION_MARKER = "[redacted]"

SECRET_PATTERNS = (
    re.compile(r"https://(?:canary\.)?discord\.com/api/webhooks/\S+", re.IGNORECASE),
    re.compile(r"\bsk-(?:or-|proj-)?[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{12,}\b"),
    re.compile(r"\b" + "ghp" + r"_[A-Za-z0-9_]{12,}\b"),
    re.compile(r"authorization:\s*bearer\s+\S+", re.IGNORECASE),
    re.compile(r"(?im)^(.*(?:api[_-]?key|token|secret|password).*)$"),
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
        re.IGNORECASE,
    ),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.IGNORECASE),
)


def redact_text(text: str) -> str:
    """Redact common secret-like values from report text."""

    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(REDACTION_MARKER, redacted)
    return redacted
