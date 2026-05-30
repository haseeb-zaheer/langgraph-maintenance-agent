"""Path helpers for local report output."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path


def report_filename(run_date: date, filename_prefix: str) -> str:
    """Return the default date-based Markdown report filename."""

    return f"{run_date.isoformat()}-{filename_prefix}.md"


def timestamped_report_filename(run_at: datetime, filename_prefix: str) -> str:
    """Return a timestamped Markdown report filename."""

    return f"{run_at:%Y%m%d-%H%M%S}-{filename_prefix}.md"


def latest_report_path(output_dir: Path) -> Path:
    """Return the latest report path for an output directory."""

    return output_dir / "latest.md"


def choose_report_path(
    output_dir: Path,
    *,
    run_date: date,
    run_at: datetime,
    filename_prefix: str,
) -> Path:
    """Choose a report path without overwriting an existing date report."""

    date_path = output_dir / report_filename(run_date, filename_prefix)
    if not date_path.exists():
        return date_path
    return output_dir / timestamped_report_filename(run_at, filename_prefix)


def ensure_output_dir(output_dir: Path) -> Path:
    """Create and return a local report output directory."""

    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir
