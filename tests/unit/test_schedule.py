from datetime import UTC, datetime, timedelta

from ffforecast.config import PollWindow
from ffforecast.schedule import due, interval_min

WINDOWS = (PollWindow(4 * 60 + 30, 9 * 60, 20), PollWindow(16 * 60, 21 * 60, 20))


def at(h, m=0):
    return datetime(2026, 10, 3, h, m, tzinfo=UTC)


def test_the_interval_is_short_inside_a_window_and_long_outside():
    assert interval_min(at(5), WINDOWS, 180) == 20
    assert interval_min(at(17, 59), WINDOWS, 180) == 20
    assert interval_min(at(12), WINDOWS, 180) == 180
    assert interval_min(at(9), WINDOWS, 180) == 180  # the end of a window is outside it
    assert (
        interval_min(at(4, 29), WINDOWS, 180) == 180 and interval_min(at(4, 30), WINDOWS, 180) == 20
    )


def test_overlapping_windows_use_the_shortest():
    w = (PollWindow(0, 600, 30), PollWindow(300, 400, 10))
    assert interval_min(at(5, 30), w, 180) == 10


def test_never_checked_means_due():
    assert due(at(12), None, WINDOWS, 180)


def test_due_after_the_interval_with_a_minute_of_slack():
    assert not due(at(5, 10), at(5, 0), WINDOWS, 180)
    assert due(at(5, 19), at(5, 0), WINDOWS, 180)  # launchd may start a few seconds early
    assert due(at(5, 25), at(5, 0), WINDOWS, 180)


def test_outside_a_window_a_check_is_due_every_three_hours():
    assert not due(at(12), at(10), WINDOWS, 180)
    assert due(at(13), at(10), WINDOWS, 180)


def test_a_check_made_hours_ago_is_due_on_entering_a_window():
    assert due(at(4, 30), at(1, 0) - timedelta(hours=0), WINDOWS, 180)
