"""Bar invariants (R-6.6.b) and the timestamp convention (R-6.4.g)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from atlas_core.domain.bar import Bar, BarValidationError, last_complete_bar_open
from atlas_core.domain.money import Price

TS = datetime(2026, 9, 16, 14, 31, tzinfo=UTC)


def make_bar(**overrides: object) -> Bar:
    kwargs: dict[str, object] = {
        "symbol": "AAPL",
        "ts": TS,
        "open": Price("100.00"),
        "high": Price("101.00"),
        "low": Price("99.50"),
        "close": Price("100.75"),
        "volume": 12_000,
    }
    kwargs.update(overrides)
    return Bar(**kwargs)  # type: ignore[arg-type]


def test_valid_bar_is_accepted() -> None:
    assert make_bar().volume == 12_000


def test_low_above_high_is_rejected() -> None:
    with pytest.raises(BarValidationError, match="low .* > high"):
        make_bar(low=Price("102.00"))


@pytest.mark.parametrize("field", ["open", "close"])
def test_open_and_close_must_sit_inside_the_range(field: str) -> None:
    with pytest.raises(BarValidationError, match="outside"):
        make_bar(**{field: Price("150.00")})


def test_negative_volume_is_rejected() -> None:
    with pytest.raises(BarValidationError, match="negative volume"):
        make_bar(volume=-1)


def test_negative_trade_count_is_rejected() -> None:
    with pytest.raises(BarValidationError, match="negative trade_count"):
        make_bar(trade_count=-1)


def test_naive_timestamp_is_rejected() -> None:
    """R-5.4.a -- a bar at an unknown offset is a bar in an unknown minute."""
    with pytest.raises(ValueError, match="naive datetime"):
        make_bar(ts=datetime(2026, 9, 16, 14, 31))  # noqa: DTZ001


def test_zero_volume_is_allowed() -> None:
    """A minute with no trades is real and must survive ingest.

    Dropping it would leave a silent hole in the series, which R-6.5.b treats as
    a defect precisely because a feature window containing a missing bar is wrong
    in a way nothing downstream notices.
    """
    assert make_bar(volume=0).volume == 0


def test_dollar_volume_prefers_vwap() -> None:
    """Close x volume misstates a trending bar; VWAP is what A8 should rank on."""
    with_vwap = make_bar(vwap=Price("100.00"))
    assert with_vwap.dollar_volume == 100 * 12_000
    assert make_bar().dollar_volume == Price("100.75").amount * 12_000


# ------------------------------------------------------------------ R-6.4.g

SESSION_OPEN = datetime(2026, 9, 16, 13, 30, tzinfo=UTC)  # 09:30 ET
MINUTE = timedelta(minutes=1)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        # Before the first bar has closed there is nothing complete to use.
        (SESSION_OPEN, None),
        (SESSION_OPEN + timedelta(seconds=59), None),
        # At exactly 13:31:00 the bar stamped 13:30 has just closed.
        (SESSION_OPEN + MINUTE, SESSION_OPEN),
        (SESSION_OPEN + timedelta(minutes=1, seconds=59), SESSION_OPEN),
        (SESSION_OPEN + timedelta(minutes=2), SESSION_OPEN + MINUTE),
        (SESSION_OPEN + timedelta(minutes=30), SESSION_OPEN + timedelta(minutes=29)),
    ],
)
def test_last_complete_bar_is_never_the_one_still_forming(
    now: datetime, expected: datetime | None
) -> None:
    """The off-by-one that makes intraday backtests look brilliant.

    At 13:31:30 the bar stamped 13:31 is half-built -- its high, low, and close
    are not yet knowable. Using it is lookahead. The answer is 13:30.
    """
    assert last_complete_bar_open(now, bar_interval=MINUTE, session_open=SESSION_OPEN) == expected


def test_decision_bar_is_strictly_before_the_current_minute() -> None:
    """Stated as an invariant rather than a table, because this is the rule."""
    for offset in range(1, 200):
        now = SESSION_OPEN + timedelta(seconds=offset)
        result = last_complete_bar_open(now, bar_interval=MINUTE, session_open=SESSION_OPEN)
        if result is not None:
            assert result + MINUTE <= now, (
                f"at {now.isoformat()} the bar stamped {result.isoformat()} "
                "had not finished forming (R-6.4.g)"
            )


def test_bar_interval_must_be_positive() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        last_complete_bar_open(SESSION_OPEN, bar_interval=timedelta(0), session_open=SESSION_OPEN)
