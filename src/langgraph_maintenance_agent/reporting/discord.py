"""Optional Discord webhook delivery."""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from langgraph_maintenance_agent.reporting.redaction import redact_text

DISCORD_CONTENT_LIMIT = 2000
DISCORD_INTERNAL_CHUNK_LIMIT = 1900
WEBHOOK_ENV_VARS = (
    "LANGGRAPH_MAINTENANCE_DISCORD_WEBHOOK_URL",
    "DISCORD_WEBHOOK_URL",
)


class DiscordDeliveryError(RuntimeError):
    """Raised when Discord delivery cannot complete."""


@dataclass(frozen=True)
class DiscordSendResult:
    """Non-sensitive Discord delivery result."""

    messages_sent: int


def load_webhook_url() -> str:
    """Load Discord webhook URL from supported environment variables."""

    for name in WEBHOOK_ENV_VARS:
        value = os.getenv(name)
        if value:
            return value
    raise DiscordDeliveryError(
        "Discord webhook URL is not configured; set "
        "LANGGRAPH_MAINTENANCE_DISCORD_WEBHOOK_URL or DISCORD_WEBHOOK_URL"
    )


def chunk_discord_content(
    content: str,
    *,
    limit: int = DISCORD_INTERNAL_CHUNK_LIMIT,
) -> list[str]:
    """Split content into Discord-safe chunks, preserving all text."""

    if limit <= 20 or limit > DISCORD_CONTENT_LIMIT:
        raise ValueError("limit must leave room for chunk prefixes")
    if len(content) <= limit:
        return [content]
    chunks: list[str] = []
    remaining = content
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        split_at = _find_split(remaining, limit)
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:]
    if len(chunks) == 1:
        return chunks
    total = len(chunks)
    prefixed: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        prefix = f"({index}/{total}) "
        available = DISCORD_CONTENT_LIMIT - len(prefix)
        if len(chunk) > available:
            raise ValueError("chunk prefix would exceed Discord content limit")
        prefixed.append(prefix + chunk)
    return prefixed


def send_discord_content(
    content: str,
    *,
    webhook_url: str | None = None,
    http_client: httpx.Client | None = None,
) -> DiscordSendResult:
    """Send redacted content to Discord as one or more webhook messages."""

    resolved_webhook = webhook_url or load_webhook_url()
    redacted_content = redact_text(content)
    chunks = chunk_discord_content(redacted_content)
    client = http_client or httpx.Client(timeout=30)
    close_client = http_client is None
    try:
        for chunk in chunks:
            response = client.post(resolved_webhook, json={"content": chunk})
            if response.status_code >= 400:
                raise DiscordDeliveryError(
                    f"Discord webhook returned HTTP {response.status_code}"
                )
    finally:
        if close_client:
            client.close()
    return DiscordSendResult(messages_sent=len(chunks))


def _find_split(content: str, limit: int) -> int:
    window = content[:limit]
    for marker in ("\n\n", "\n", " "):
        index = window.rfind(marker)
        if index >= limit // 2:
            return index + len(marker)
    return limit
