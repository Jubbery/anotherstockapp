"""R-6.4.b / R-6.4.c — no survivorship bias.

§9.1 row L4. The universe for a past date comes from the snapshot taken on that
date, including companies that have since delisted. Building it from today's
asset list silently removes every failure, which does not look like a bug.
"""

from __future__ import annotations

from datetime import date

import pytest

from atlas_core.pit import (
    SurvivorshipError,
    UniverseEntry,
    UniverseSnapshot,
    assert_retains_delistings,
)

pytestmark = pytest.mark.leakage


def entry(symbol: str, *, tradable: bool = True, delisted: date | None = None) -> UniverseEntry:
    return UniverseEntry(
        symbol=symbol,
        tradable=tradable,
        shortable=True,
        easy_to_borrow=True,
        marginable=True,
        delisted_at=delisted,
    )


def test_a_snapshot_retains_symbols_that_later_delisted() -> None:
    """The 2023 universe must still contain names that no longer exist."""
    snapshot = UniverseSnapshot.build(
        date(2023, 6, 1),
        [entry("AAPL"), entry("SIVB"), entry("FRC"), entry("CS")],
    )
    assert snapshot.contains("SIVB"), (
        "a bank that failed in 2023 was tradeable in the 2023 universe; removing it "
        "is exactly the bias R-6.4.b exists to prevent"
    )
    assert len(snapshot) == 4


def test_a_symbol_delisted_by_the_snapshot_date_is_present_but_not_eligible() -> None:
    """Retained for history (R-6.4.c), excluded from trading."""
    snapshot = UniverseSnapshot.build(
        date(2024, 1, 2), [entry("AAPL"), entry("SIVB", delisted=date(2023, 5, 1))]
    )
    assert snapshot.contains("SIVB")
    assert "SIVB" not in {e.symbol for e in snapshot.eligible()}
    assert snapshot.delisted()[0].symbol == "SIVB"


def test_an_untradeable_symbol_is_not_eligible() -> None:
    snapshot = UniverseSnapshot.build(date(2026, 9, 16), [entry("HALT", tradable=False)])
    assert snapshot.eligible() == ()


def test_snapshots_are_ordered_and_reject_duplicates() -> None:
    """Determinism: Stage A must produce byte-identical output (R-7.1.a)."""
    snapshot = UniverseSnapshot.build(date(2026, 9, 16), [entry("MSFT"), entry("AAPL")])
    assert snapshot.symbols() == ("AAPL", "MSFT")

    with pytest.raises(ValueError, match="duplicate symbols"):
        UniverseSnapshot.build(date(2026, 9, 16), [entry("AAPL"), entry("AAPL")])


def test_a_universe_with_no_delistings_trips_the_smoke_alarm() -> None:
    """The signature of a universe rebuilt from today's asset list."""
    clean = [
        UniverseSnapshot.build(date(2023, m, 1), [entry("AAPL"), entry("MSFT")])
        for m in range(1, 13)
    ]
    with pytest.raises(SurvivorshipError, match="survivorship bias"):
        assert_retains_delistings(clean)


def test_a_realistic_universe_passes_the_smoke_alarm() -> None:
    snapshots = [
        UniverseSnapshot.build(date(2023, 1, 1), [entry("AAPL"), entry("SIVB")]),
        UniverseSnapshot.build(
            date(2023, 6, 1), [entry("AAPL"), entry("SIVB", delisted=date(2023, 5, 1))]
        ),
    ]
    assert_retains_delistings(snapshots)


def test_snapshot_is_immutable() -> None:
    """A snapshot that can be edited afterwards is one that can acquire hindsight."""
    snapshot = UniverseSnapshot.build(date(2026, 9, 16), [entry("AAPL")])
    with pytest.raises(AttributeError):
        snapshot.as_of = date(2026, 9, 17)  # type: ignore[misc]
