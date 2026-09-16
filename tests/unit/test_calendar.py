"""R-5.4.c / R-12.4.d — session arithmetic, and the half-day that costs money.

The case that matters: on the day after US Thanksgiving the NYSE closes at
13:00 ET. An engine that force-flattens at a hardcoded 15:55 has held a position
through the close for nearly three hours, on a day Atlas is supposed to end flat.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from atlas_core.calendar import MarketCalendar, Session, UnknownSessionError

# 2026-09-16, a normal Wednesday: 09:30-16:00 ET = 13:30-20:00 UTC.
NORMAL = Session(
    session_date=date(2026, 9, 16),
    is_trading_day=True,
    open_at=datetime(2026, 9, 16, 13, 30, tzinfo=UTC),
    close_at=datetime(2026, 9, 16, 20, 0, tzinfo=UTC),
)

# 2026-11-27, the day after Thanksgiving: 09:30-13:00 ET = 14:30-18:00 UTC.
# (November is EST, so the UTC offset differs from September's EDT.)
HALF_DAY = Session(
    session_date=date(2026, 11, 27),
    is_trading_day=True,
    open_at=datetime(2026, 11, 27, 14, 30, tzinfo=UTC),
    close_at=datetime(2026, 11, 27, 18, 0, tzinfo=UTC),
    is_half_day=True,
)

THANKSGIVING = Session(session_date=date(2026, 11, 26), is_trading_day=False)
WEEKEND = Session(session_date=date(2026, 11, 28), is_trading_day=False)

CALENDAR = MarketCalendar.build([NORMAL, THANKSGIVING, HALF_DAY, WEEKEND])

OFFSETS = {
    "opening_range": timedelta(minutes=15),
    "no_new_entries_before_close": timedelta(minutes=15),
    "flatten_before_close": timedelta(minutes=5),
}


def test_normal_day_times() -> None:
    times = CALENDAR.session_times(date(2026, 9, 16), **OFFSETS)
    assert times.entry_window_opens_at == datetime(2026, 9, 16, 13, 45, tzinfo=UTC)  # 09:45 ET
    assert times.no_new_entries_after == datetime(2026, 9, 16, 19, 45, tzinfo=UTC)  # 15:45 ET
    assert times.force_flatten_at == datetime(2026, 9, 16, 19, 55, tzinfo=UTC)  # 15:55 ET
    assert not times.is_half_day


def test_half_day_flatten_moves_with_the_close() -> None:
    """R-12.4.d. This is the test that stops an overnight position.

    A hardcoded 15:55 ET flatten on this day would fire 2h55m after the market
    had already closed.
    """
    times = CALENDAR.session_times(date(2026, 11, 27), **OFFSETS)
    assert times.close_at == datetime(2026, 11, 27, 18, 0, tzinfo=UTC)  # 13:00 ET
    assert times.force_flatten_at == datetime(2026, 11, 27, 17, 55, tzinfo=UTC)  # 12:55 ET
    assert times.no_new_entries_after == datetime(2026, 11, 27, 17, 45, tzinfo=UTC)
    assert times.is_half_day

    normal = CALENDAR.session_times(date(2026, 9, 16), **OFFSETS)
    assert times.force_flatten_at.time() != normal.force_flatten_at.time()


def test_flatten_is_always_before_the_close() -> None:
    """Stated as an invariant over every session in the calendar."""
    for day in (date(2026, 9, 16), date(2026, 11, 27)):
        times = CALENDAR.session_times(day, **OFFSETS)
        assert times.force_flatten_at < times.close_at
        assert times.no_new_entries_after <= times.force_flatten_at
        assert times.entry_window_opens_at < times.no_new_entries_after


def test_an_unknown_date_raises_rather_than_guessing() -> None:
    """R-5.4.c. A guessed close is the whole hazard."""
    with pytest.raises(UnknownSessionError, match="Refusing to guess"):
        CALENDAR.session_times(date(2030, 1, 2), **OFFSETS)


def test_a_holiday_has_no_session_times() -> None:
    with pytest.raises(UnknownSessionError, match="not a trading day"):
        CALENDAR.session_times(date(2026, 11, 26), **OFFSETS)


def test_trading_days_skips_holidays_and_weekends() -> None:
    days = CALENDAR.trading_days(date(2026, 11, 26), date(2026, 11, 28))
    assert days == (date(2026, 11, 27),)


def test_a_gap_in_the_calendar_raises_rather_than_shortening_a_window() -> None:
    """A 20-session average computed over 18 sessions is wrong, quietly."""
    with pytest.raises(UnknownSessionError):
        CALENDAR.trading_days(date(2026, 11, 25), date(2026, 11, 28))


def test_previous_trading_day_walks_over_the_holiday() -> None:
    assert CALENDAR.previous_trading_day(date(2026, 11, 28)) == date(2026, 11, 27)


def test_previous_trading_day_gives_up_rather_than_looping() -> None:
    sparse = MarketCalendar.build([NORMAL])
    with pytest.raises(UnknownSessionError):
        sparse.previous_trading_day(date(2026, 9, 16))


def test_flatten_offset_must_be_positive() -> None:
    """Flattening at or after the close is holding overnight."""
    with pytest.raises(ValueError, match="holding overnight"):
        CALENDAR.session_times(
            date(2026, 9, 16),
            opening_range=timedelta(minutes=15),
            no_new_entries_before_close=timedelta(minutes=15),
            flatten_before_close=timedelta(0),
        )


def test_entries_must_stop_before_the_flatten() -> None:
    """Otherwise the engine can open a position it must immediately close."""
    with pytest.raises(ValueError, match="at least flatten_before_close"):
        CALENDAR.session_times(
            date(2026, 9, 16),
            opening_range=timedelta(minutes=15),
            no_new_entries_before_close=timedelta(minutes=1),
            flatten_before_close=timedelta(minutes=5),
        )


def test_an_empty_entry_window_is_refused() -> None:
    """Real on a short session with generous offsets. Better loud than silent."""
    with pytest.raises(ValueError, match="entry window is empty"):
        CALENDAR.session_times(
            date(2026, 11, 27),
            opening_range=timedelta(hours=3),
            no_new_entries_before_close=timedelta(minutes=30),
            flatten_before_close=timedelta(minutes=5),
        )


def test_a_trading_day_without_times_is_rejected() -> None:
    with pytest.raises(ValueError, match="needs open and close"):
        Session(session_date=date(2026, 9, 16), is_trading_day=True)


def test_a_holiday_with_times_is_rejected() -> None:
    with pytest.raises(ValueError, match="no session times"):
        Session(
            session_date=date(2026, 12, 25),
            is_trading_day=False,
            open_at=datetime(2026, 12, 25, 14, 30, tzinfo=UTC),
        )


def test_close_must_follow_open() -> None:
    with pytest.raises(ValueError, match="not after open"):
        Session(
            session_date=date(2026, 9, 16),
            is_trading_day=True,
            open_at=datetime(2026, 9, 16, 20, 0, tzinfo=UTC),
            close_at=datetime(2026, 9, 16, 13, 30, tzinfo=UTC),
        )


def test_duplicate_calendar_rows_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate calendar row"):
        MarketCalendar.build([NORMAL, NORMAL])


def test_half_day_is_shorter() -> None:
    assert CALENDAR.session(date(2026, 11, 27)).duration == timedelta(hours=3, minutes=30)
    assert CALENDAR.session(date(2026, 9, 16)).duration == timedelta(hours=6, minutes=30)


def test_no_session_times_are_hardcoded_in_the_calendar_module() -> None:
    """R-5.4.c, enforced against the module that would be most tempted to.

    Docstrings stripped: the module explains the half-day hazard by naming the
    times it must not contain.
    """
    import ast
    from pathlib import Path

    tree = ast.parse(Path("libs/atlas_core/calendar/session.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node.value = ""
    code = ast.unparse(tree)

    for forbidden in ("9, 30", "16, 0", "15, 55", "15, 45", "13, 0"):
        assert forbidden not in code, f"hardcoded session time {forbidden!r} (R-5.4.c)"
