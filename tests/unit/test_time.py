"""R-5.4: timezone-aware UTC in storage, New York only at display."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from atlas_core.domain.time import ensure_utc, format_for_display, utc_now
from atlas_core.testing import FrozenClock


def test_utc_now_is_aware() -> None:
    assert utc_now().tzinfo is not None


def test_naive_datetime_is_rejected() -> None:
    """A naive datetime is an unknown offset, not 'probably UTC'."""
    with pytest.raises(ValueError, match="naive datetime"):
        ensure_utc(datetime(2026, 9, 16, 14, 30))  # noqa: DTZ001


def test_aware_non_utc_is_converted() -> None:
    ny = datetime(2026, 9, 16, 9, 30, tzinfo=ZoneInfo("America/New_York"))
    assert ensure_utc(ny) == datetime(2026, 9, 16, 13, 30, tzinfo=UTC)


def test_display_is_always_labelled() -> None:
    """R-15.4.a: a time shown without its zone is a defect."""
    rendered = format_for_display(datetime(2026, 9, 16, 13, 30, tzinfo=UTC))
    assert "09:30:00" in rendered
    assert rendered.endswith(("EDT", "EST"))


def test_frozen_clock_does_not_move_on_its_own() -> None:
    clock = FrozenClock(datetime(2026, 9, 16, 13, 30, tzinfo=UTC))
    first = clock.now()
    assert clock.now() == first
    clock.advance(timedelta(minutes=1))
    assert clock.now() == first + timedelta(minutes=1)


def test_frozen_clock_rejects_naive_start() -> None:
    with pytest.raises(ValueError, match="naive datetime"):
        FrozenClock(datetime(2026, 9, 16, 13, 30))  # noqa: DTZ001


def test_time_does_not_run_backwards() -> None:
    clock = FrozenClock(datetime(2026, 9, 16, 13, 30, tzinfo=UTC))
    with pytest.raises(ValueError, match="does not run backwards"):
        clock.advance(timedelta(seconds=-1))


def test_no_hardcoded_session_times_in_the_time_module() -> None:
    """R-5.4.c: half-days exist, so session boundaries come from the calendar.

    Docstrings are stripped before the check -- the module explains the rule by
    quoting the pattern it forbids, and a grep over raw source would flag that.
    """
    import ast
    from pathlib import Path

    tree = ast.parse(Path("libs/atlas_core/domain/time.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node.value = ""
    code = ast.unparse(tree)

    for forbidden in ("9, 30", "16, 0", "15, 55", "15, 45"):
        assert (
            forbidden not in code
        ), f"hardcoded session time {forbidden!r} -- use the exchange calendar (R-5.4.c)"
