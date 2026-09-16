"""R-6.4.h — a ticker is not an identity.

The read-path counterpart to ``tests/integration/test_instrument_identity.py``,
which proves the same rules at the storage layer. Both exist because the
constraint and the resolver are two independent chances to get this wrong.

Filed under leakage because the ticker-reuse case behaves like every other row
in §9.1: it does not raise, and the feature it manufactures looks good.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from atlas_core.pit import (
    AmbiguousSymbolError,
    SymbolMapping,
    SymbolResolver,
    UnknownSymbolError,
)

pytestmark = pytest.mark.leakage

NOW = datetime(2026, 9, 16, tzinfo=UTC)

META = 1
OLD_XYZ = 2
NEW_XYZ = 3

# FB -> META, announced 2022-06-01, effective 2022-06-09.
RENAME = SymbolResolver.build(
    [
        SymbolMapping(
            "FB", META, date(2012, 5, 18), date(2022, 6, 9), datetime(2012, 5, 18, tzinfo=UTC)
        ),
        SymbolMapping("META", META, date(2022, 6, 9), None, datetime(2022, 6, 1, tzinfo=UTC)),
    ]
)

# XYZ delisted 2018-03-01; the ticker is reassigned to a different company in 2021.
REUSE = SymbolResolver.build(
    [
        SymbolMapping(
            "XYZ", OLD_XYZ, date(2005, 1, 1), date(2018, 3, 1), datetime(2005, 1, 1, tzinfo=UTC)
        ),
        SymbolMapping("XYZ", NEW_XYZ, date(2021, 6, 1), None, datetime(2021, 6, 1, tzinfo=UTC)),
    ]
)


def test_a_rename_preserves_one_identity() -> None:
    """The point of the surrogate key."""
    before = RENAME.resolve("FB", as_of=date(2020, 1, 2), knowledge_cutoff=NOW)
    after = RENAME.resolve("META", as_of=date(2024, 1, 2), knowledge_cutoff=NOW)
    assert before == after == META


def test_the_changeover_is_half_open() -> None:
    """On the effective date the new ticker is live and the old one is not."""
    changeover = date(2022, 6, 9)
    assert RENAME.resolve("META", as_of=changeover, knowledge_cutoff=NOW) == META
    with pytest.raises(UnknownSymbolError):
        RENAME.resolve("FB", as_of=changeover, knowledge_cutoff=NOW)

    day_before = date(2022, 6, 8)
    assert RENAME.resolve("FB", as_of=day_before, knowledge_cutoff=NOW) == META
    with pytest.raises(UnknownSymbolError):
        RENAME.resolve("META", as_of=day_before, knowledge_cutoff=NOW)


def test_a_reused_ticker_resolves_to_different_instruments() -> None:
    """The dangerous case. Keyed by symbol these are one continuous series."""
    then = REUSE.resolve("XYZ", as_of=date(2010, 1, 1), knowledge_cutoff=NOW)
    now = REUSE.resolve("XYZ", as_of=date(2024, 1, 1), knowledge_cutoff=NOW)
    assert then == OLD_XYZ
    assert now == NEW_XYZ
    assert then != now


def test_a_dead_ticker_raises_rather_than_falling_back() -> None:
    """Nobody quoted XYZ in 2019, and the honest answer is no answer.

    Returning the current mapping instead is exactly how the reuse bug gets in:
    a 2019 bar would be filed under the company that took the ticker in 2021.
    """
    with pytest.raises(UnknownSymbolError, match="Refusing to fall back"):
        REUSE.resolve("XYZ", as_of=date(2019, 1, 1), knowledge_cutoff=NOW)


def test_resolution_respects_knowledge_time() -> None:
    """R-6.4.a. Meta announced on 2022-06-01, effective 2022-06-09.

    A backtest running on 2022-05-01 had not heard of the ticker yet.
    """
    unaware = datetime(2022, 5, 1, tzinfo=UTC)
    with pytest.raises(UnknownSymbolError):
        RENAME.resolve("META", as_of=date(2022, 6, 10), knowledge_cutoff=unaware)

    aware = datetime(2022, 6, 2, tzinfo=UTC)
    assert RENAME.resolve("META", as_of=date(2022, 6, 10), knowledge_cutoff=aware) == META


def test_an_unknown_ticker_raises() -> None:
    with pytest.raises(UnknownSymbolError):
        RENAME.resolve("NOPE", as_of=date(2024, 1, 1), knowledge_cutoff=NOW)


def test_overlapping_mappings_raise_rather_than_picking_one() -> None:
    """The database refuses to store this; the resolver refuses to guess past it."""
    broken = SymbolResolver.build(
        [
            SymbolMapping(
                "XYZ", OLD_XYZ, date(2005, 1, 1), date(2018, 3, 1), datetime(2005, 1, 1, tzinfo=UTC)
            ),
            SymbolMapping(
                "XYZ", NEW_XYZ, date(2010, 1, 1), date(2012, 1, 1), datetime(2010, 1, 1, tzinfo=UTC)
            ),
        ]
    )
    with pytest.raises(AmbiguousSymbolError, match="refused at write time"):
        broken.resolve("XYZ", as_of=date(2011, 1, 1), knowledge_cutoff=NOW)


def test_reverse_lookup_gives_the_contemporaneous_ticker() -> None:
    """A report about 2020 should say FB, because that is what it was called."""
    assert RENAME.symbol_for(META, as_of=date(2020, 1, 2), knowledge_cutoff=NOW) == "FB"
    assert RENAME.symbol_for(META, as_of=date(2024, 1, 2), knowledge_cutoff=NOW) == "META"


def test_reverse_lookup_raises_before_the_instrument_existed() -> None:
    with pytest.raises(UnknownSymbolError):
        RENAME.symbol_for(META, as_of=date(2000, 1, 1), knowledge_cutoff=NOW)


def test_history_is_ordered() -> None:
    history = RENAME.history(META)
    assert [mapping.symbol for mapping in history] == ["FB", "META"]


def test_an_inverted_range_is_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="must be after"):
        SymbolMapping("XYZ", 1, date(2020, 1, 1), date(2019, 1, 1), NOW)


def test_a_naive_knowledge_time_is_rejected() -> None:
    with pytest.raises(ValueError, match="naive datetime"):
        SymbolMapping("XYZ", 1, date(2020, 1, 1), None, datetime(2020, 1, 1))  # noqa: DTZ001


def test_resolver_is_immutable() -> None:
    """A resolver extendable mid-backtest is one that can acquire hindsight."""
    with pytest.raises(AttributeError):
        RENAME.mappings = ()  # type: ignore[misc]
