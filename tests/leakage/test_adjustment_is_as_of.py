"""R-6.4.d / R-6.4.e — split adjustment is as-of, not retroactive.

§9.1 row L5. This is the failure where a split today silently rewrites the past,
so that a model trained on Tuesday saw a different history than the same model
trained on Monday, and neither matches what a contemporaneous observer saw.

The scenario throughout: **NVDA-like, 10-for-1 split effective 2026-06-10.**
Before the split the stock traded near $1,200; after, near $120.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from atlas_core.domain.bar import Bar
from atlas_core.domain.corporate_action import ActionType, CorporateAction
from atlas_core.domain.money import Money, Price
from atlas_core.pit import adjust_bar, adjustment_factors, knowable_actions

SPLIT_DATE = date(2026, 6, 10)
ANNOUNCED_AT = datetime(2026, 5, 22, 20, 5, tzinfo=UTC)

SPLIT = CorporateAction(
    symbol="NVDA",
    action_type=ActionType.SPLIT,
    effective_at=SPLIT_DATE,
    knowledge_at=ANNOUNCED_AT,
    ratio=Decimal(10),
)

PRE_SPLIT_BAR = Bar(
    symbol="NVDA",
    ts=datetime(2026, 6, 1, 20, 0, tzinfo=UTC),
    open=Price("1200.00"),
    high=Price("1215.00"),
    low=Price("1190.00"),
    close=Price("1210.00"),
    volume=2_000_000,
    vwap=Price("1205.00"),
    trade_count=41_000,
)

pytestmark = pytest.mark.leakage


def test_viewed_before_the_split_prices_are_raw() -> None:
    """The heart of R-6.4.e.

    On 2026-06-05 NVDA was a $1,210 stock. A Stage A scan that day must see
    $1,210 -- not $121 -- or rule A10's price band and A8's dollar-volume filter
    are being applied to a stock that did not exist yet.
    """
    adjusted = adjust_bar(
        PRE_SPLIT_BAR,
        [SPLIT],
        as_of=date(2026, 6, 5),
        knowledge_cutoff=datetime(2026, 6, 5, 12, 0, tzinfo=UTC),
    )
    assert adjusted.close == Price("1210.00")
    assert adjusted.volume == 2_000_000
    assert adjusted is PRE_SPLIT_BAR, "identity adjustment should not copy"


def test_viewed_after_the_split_prices_are_adjusted() -> None:
    """From 2026-06-11 the same bar is comparable with post-split prices."""
    adjusted = adjust_bar(
        PRE_SPLIT_BAR,
        [SPLIT],
        as_of=date(2026, 6, 11),
        knowledge_cutoff=datetime(2026, 6, 11, 12, 0, tzinfo=UTC),
    )
    assert adjusted.close == Price("121.00")
    assert adjusted.open == Price("120.00")
    assert adjusted.high == Price("121.50")
    assert adjusted.low == Price("119.00")
    assert adjusted.vwap == Price("120.50")
    assert adjusted.volume == 20_000_000
    assert adjusted.trade_count == 41_000, "a split does not change the number of trades"


def test_the_same_bar_yields_different_series_at_different_vantage_points() -> None:
    """Stated directly, because it is the property the whole design exists for."""
    before = adjust_bar(
        PRE_SPLIT_BAR,
        [SPLIT],
        as_of=date(2026, 6, 9),
        knowledge_cutoff=datetime(2026, 6, 9, tzinfo=UTC),
    )
    after = adjust_bar(
        PRE_SPLIT_BAR,
        [SPLIT],
        as_of=date(2026, 6, 10),
        knowledge_cutoff=datetime(2026, 6, 10, tzinfo=UTC),
    )
    assert before.close.amount == after.close.amount * 10


def test_a_split_on_the_bars_own_date_is_already_in_the_raw_prices() -> None:
    """Boundary: ``bar_date < effective_at``, strictly.

    The bar printed *on* the ex-date already trades post-split. Adjusting it
    again divides by ten twice and produces a 90% one-day crash that never
    happened -- which a momentum feature would read as a signal.
    """
    ex_date_bar = Bar(
        symbol="NVDA",
        ts=datetime(2026, 6, 10, 20, 0, tzinfo=UTC),
        open=Price("120.00"),
        high=Price("122.00"),
        low=Price("119.00"),
        close=Price("121.00"),
        volume=20_000_000,
    )
    adjusted = adjust_bar(
        ex_date_bar,
        [SPLIT],
        as_of=date(2026, 7, 1),
        knowledge_cutoff=datetime(2026, 7, 1, tzinfo=UTC),
    )
    assert adjusted.close == Price("121.00")


def test_an_action_we_had_not_learned_of_is_not_applied() -> None:
    """R-6.4.a. Knowledge time is independent of effective time.

    A vendor backfill can deliver a corporate action days after its ex-date. A
    backtest running at 2026-06-11 with a knowledge cutoff before the
    announcement must behave as we did: unaware.
    """
    factors = adjustment_factors(
        [SPLIT],
        bar_date=date(2026, 6, 1),
        as_of=date(2026, 6, 11),
        knowledge_cutoff=datetime(2026, 5, 1, tzinfo=UTC),  # before it was announced
    )
    assert factors.is_identity


def test_knowable_actions_uses_the_same_filter() -> None:
    assert knowable_actions([SPLIT], knowledge_cutoff=ANNOUNCED_AT) == [SPLIT]
    assert knowable_actions([SPLIT], knowledge_cutoff=datetime(2026, 5, 1, tzinfo=UTC)) == []


def test_reverse_split_inflates_prices_not_deflates() -> None:
    """1-for-10 in a distressed name.

    Naive handling turns a compliance-driven reverse split into a 900% gain, and
    a momentum ranker would put it at the top of the list.
    """
    reverse = CorporateAction(
        symbol="ZZZZ",
        action_type=ActionType.SPLIT,
        effective_at=SPLIT_DATE,
        knowledge_at=ANNOUNCED_AT,
        ratio=Decimal("0.1"),
    )
    assert reverse.is_reverse_split
    bar = Bar(
        symbol="ZZZZ",
        ts=datetime(2026, 6, 1, 20, 0, tzinfo=UTC),
        open=Price("0.50"),
        high=Price("0.55"),
        low=Price("0.48"),
        close=Price("0.52"),
        volume=5_000_000,
    )
    adjusted = adjust_bar(
        bar,
        [reverse],
        as_of=date(2026, 7, 1),
        knowledge_cutoff=datetime(2026, 7, 1, tzinfo=UTC),
    )
    assert adjusted.close == Price("5.2")
    assert adjusted.volume == 500_000


def test_multiple_splits_compound() -> None:
    second = CorporateAction(
        symbol="NVDA",
        action_type=ActionType.SPLIT,
        effective_at=date(2026, 8, 1),
        knowledge_at=datetime(2026, 7, 1, tzinfo=UTC),
        ratio=Decimal(2),
    )
    factors = adjustment_factors(
        [SPLIT, second],
        bar_date=date(2026, 6, 1),
        as_of=date(2026, 9, 1),
        knowledge_cutoff=datetime(2026, 9, 1, tzinfo=UTC),
    )
    assert factors.price == Decimal(1) / Decimal(20)
    assert factors.volume == Decimal(20)


def test_adjustment_order_does_not_matter() -> None:
    """Multiplication commutes; assert it so a future loop rewrite cannot break it."""
    second = CorporateAction(
        symbol="NVDA",
        action_type=ActionType.SPLIT,
        effective_at=date(2026, 8, 1),
        knowledge_at=datetime(2026, 7, 1, tzinfo=UTC),
        ratio=Decimal(2),
    )
    kwargs: dict[str, Any] = {
        "bar_date": date(2026, 6, 1),
        "as_of": date(2026, 9, 1),
        "knowledge_cutoff": datetime(2026, 9, 1, tzinfo=UTC),
    }
    assert adjustment_factors([SPLIT, second], **kwargs) == adjustment_factors(
        [second, SPLIT], **kwargs
    )


def test_viewing_a_bar_from_before_it_existed_is_an_error() -> None:
    with pytest.raises(ValueError, match="precedes bar_date"):
        adjustment_factors(
            [SPLIT],
            bar_date=date(2026, 6, 1),
            as_of=date(2026, 5, 1),
            knowledge_cutoff=datetime(2026, 6, 1, tzinfo=UTC),
        )


def test_dividends_are_off_by_default_and_require_a_reference_close() -> None:
    """Atlas holds nothing overnight, so dividends touch features, never PnL."""
    dividend = CorporateAction(
        symbol="KO",
        action_type=ActionType.DIVIDEND,
        effective_at=date(2026, 6, 10),
        knowledge_at=ANNOUNCED_AT,
        cash_amount=Money("0.49"),
    )
    kwargs: dict[str, Any] = {
        "bar_date": date(2026, 6, 1),
        "as_of": date(2026, 7, 1),
        "knowledge_cutoff": datetime(2026, 7, 1, tzinfo=UTC),
    }
    assert adjustment_factors([dividend], **kwargs).is_identity

    with pytest.raises(ValueError, match="requires reference_close"):
        adjustment_factors([dividend], include_dividends=True, **kwargs)

    factors = adjustment_factors(
        [dividend], include_dividends=True, reference_close=Price("70.00"), **kwargs
    )
    assert factors.price == Decimal(1) - (Decimal("0.49") / Decimal("70.00"))


def test_adjusted_prices_stay_decimal() -> None:
    """R-3.6.a survives the adjustment path."""
    adjusted = adjust_bar(
        PRE_SPLIT_BAR,
        [SPLIT],
        as_of=date(2026, 6, 11),
        knowledge_cutoff=datetime(2026, 6, 11, tzinfo=UTC),
    )
    assert isinstance(adjusted.close.amount, Decimal)
    assert adjusted.close.amount == Decimal("121.00")
