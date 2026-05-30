"""Text bounding helpers for logs and command excerpts."""

TRUNCATION_MARKER = "\n[truncated]"


def bound_text(text: str, limit: int) -> str:
    """Return text capped at limit characters with a clear truncation marker."""

    if limit <= len(TRUNCATION_MARKER):
        raise ValueError("limit must be larger than truncation marker")
    if len(text) <= limit:
        return text
    available = limit - len(TRUNCATION_MARKER)
    return text[:available].rstrip() + TRUNCATION_MARKER
