from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from langgraph_maintenance_agent.runtime.paths import (
    choose_report_path,
    ensure_output_dir,
    latest_report_path,
    report_filename,
    timestamped_report_filename,
)
from langgraph_maintenance_agent.runtime.text import TRUNCATION_MARKER, bound_text


def test_report_filename_uses_expected_date_format() -> None:
    assert (
        report_filename(date(2026, 1, 2), "routine-maintenance")
        == "2026-01-02-routine-maintenance.md"
    )


def test_timestamped_report_filename_uses_expected_format() -> None:
    assert (
        timestamped_report_filename(
            datetime(2026, 1, 2, 3, 4, 5),
            "routine-maintenance",
        )
        == "20260102-030405-routine-maintenance.md"
    )


def test_choose_report_path_uses_date_path_when_available(tmp_path: Path) -> None:
    path = choose_report_path(
        tmp_path,
        run_date=date(2026, 1, 2),
        run_at=datetime(2026, 1, 2, 3, 4, 5),
        filename_prefix="routine-maintenance",
    )

    assert path == tmp_path / "2026-01-02-routine-maintenance.md"


def test_choose_report_path_avoids_overwriting_existing_report(
    tmp_path: Path,
) -> None:
    existing = tmp_path / "2026-01-02-routine-maintenance.md"
    existing.write_text("existing", encoding="utf-8")

    path = choose_report_path(
        tmp_path,
        run_date=date(2026, 1, 2),
        run_at=datetime(2026, 1, 2, 3, 4, 5),
        filename_prefix="routine-maintenance",
    )

    assert path == tmp_path / "20260102-030405-routine-maintenance.md"


def test_latest_report_path_returns_latest_md(tmp_path: Path) -> None:
    assert latest_report_path(tmp_path) == tmp_path / "latest.md"


def test_ensure_output_dir_creates_directory(tmp_path: Path) -> None:
    output_dir = tmp_path / "reports"

    assert ensure_output_dir(output_dir) == output_dir
    assert output_dir.is_dir()


def test_bound_text_leaves_short_text_unchanged() -> None:
    assert bound_text("short", 20) == "short"


def test_bound_text_truncates_long_text() -> None:
    result = bound_text("0123456789" * 10, 30)

    assert len(result) <= 30
    assert result.endswith(TRUNCATION_MARKER)


def test_bound_text_rejects_too_small_limit() -> None:
    with pytest.raises(ValueError, match="limit"):
        bound_text("hello", len(TRUNCATION_MARKER))
