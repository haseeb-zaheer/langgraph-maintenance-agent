"""Tiny public-safe module for demo maintenance checks."""


def health_summary(open_issue_count: int) -> str:
    """Return a short health label for the fixture service."""

    if open_issue_count < 0:
        raise ValueError("open_issue_count must be non-negative")
    if open_issue_count == 0:
        return "clear"
    if open_issue_count <= 2:
        return "watch"
    return "needs review"


# TODO: Add a synthetic owner rotation example for static marker reporting.
