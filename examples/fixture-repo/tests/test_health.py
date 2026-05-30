from fixture_service import health_summary


def test_health_summary_for_clear_state() -> None:
    assert health_summary(0) == "clear"


def test_health_summary_for_watch_state() -> None:
    assert health_summary(2) == "watch"
