"""Heavy work must wait during Bank Health's Monday run and the CECL Lab's Wednesday run."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from scamsim.schedule_guard import CHICAGO, is_quiet_window


def chicago(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=CHICAGO)


# 30 Nov 2026 is a Monday, 1 Dec a Tuesday, 2 Dec a Wednesday.
@pytest.mark.parametrize(
    ("when", "quiet"),
    [
        (chicago(2026, 11, 29, 23, 59), False),  # Sunday night: not yet
        (chicago(2026, 11, 30, 0, 0), True),  # Monday window starts (start included)
        (chicago(2026, 11, 30, 12, 59), True),  # last blocked minute
        (chicago(2026, 11, 30, 13, 0), False),  # end excluded: allowed again
        (chicago(2026, 12, 1, 3, 0), False),  # Tuesday: no window
        (chicago(2026, 12, 1, 12, 0), False),
        (chicago(2026, 12, 2, 0, 0), True),  # Wednesday window starts
        (chicago(2026, 12, 2, 17, 59), True),  # last blocked minute
        (chicago(2026, 12, 2, 18, 0), False),  # end excluded: allowed again
        (chicago(2026, 12, 3, 9, 0), False),  # Thursday: no window
    ],
)
def test_window_edges_in_chicago_time(when: datetime, quiet: bool) -> None:
    assert is_quiet_window(when) is quiet


def test_daylight_saving_keeps_the_window_on_chicago_wall_clock() -> None:
    # Summer time starts Sunday 14 Mar 2027, so Monday 15 Mar is UTC-5 instead of UTC-6.
    # The window must still end at 13:00 Chicago time, which is now 18:00 UTC, not 19:00.
    assert is_quiet_window(datetime(2027, 3, 15, 17, 59, tzinfo=UTC)) is True  # 12:59 CDT
    assert is_quiet_window(datetime(2027, 3, 15, 18, 0, tzinfo=UTC)) is False  # 13:00 CDT
    # In winter the same 18:00 UTC is only 12:00 in Chicago, so it is still quiet.
    assert is_quiet_window(datetime(2026, 11, 30, 18, 0, tzinfo=UTC)) is True  # 12:00 CST
    assert is_quiet_window(datetime(2026, 11, 30, 19, 0, tzinfo=UTC)) is False  # 13:00 CST


def test_the_weekday_is_judged_in_chicago_not_utc() -> None:
    # Sunday 23:30 in Chicago is already Monday 05:30 UTC, but it's not Monday in Chicago yet.
    assert is_quiet_window(datetime(2026, 11, 30, 5, 30, tzinfo=UTC)) is False


def test_any_time_zone_is_converted_first() -> None:
    # 20:00 in UTC+8 on Monday 30 Nov is 06:00 Monday in Chicago: quiet.
    plus_eight = timezone(timedelta(hours=8))
    assert is_quiet_window(datetime(2026, 11, 30, 20, 0, tzinfo=plus_eight)) is True


def test_a_time_without_a_time_zone_is_refused() -> None:
    with pytest.raises(ValueError, match="time-zone-aware"):
        is_quiet_window(datetime(2026, 11, 30, 6, 0))  # no tzinfo, on purpose
