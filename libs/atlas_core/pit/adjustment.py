"""As-of split adjustment.

R-6.4.d: raw OHLCV is stored; adjusted series are **computed at read time, as of
a given date**. R-6.4.e: Stage A's price and dollar-volume filters are evaluated
on prices as they appeared on that date — unadjusted for splits that had not yet
happened.

## The arithmetic

A split on date ``E`` with ratio ``r`` (new shares per old share) makes every
price before ``E`` comparable to prices after ``E`` by dividing by ``r``; share
counts and volumes multiply by ``r``.

For a bar on date ``B``, viewed as of date ``D``, the price factor is the product
of ``1/r`` over every split with ``B < effective_at <= D`` that was knowable by
the moment we are asking.

Three windows are in play and confusing them is the whole hazard:

- ``B < effective_at`` — a split on or before the bar's own date is already
  reflected in that bar's raw prices. Applying it again double-counts.
- ``effective_at <= D`` — a split after the as-of date has not happened yet from
  the vantage point being simulated. Applying it is lookahead, and it is exactly
  the error R-6.4.e calls out: a $200 stock that later split 10:1 was not a $20
  stock at the time and must not be filtered as one.
- ``knowledge_at <= knowledge_cutoff`` — even a split that has *happened* may not
  have been in our database yet. This matters for vendor backfills, where a
  corporate action is often loaded days after its ex-date.

## Dividends

Split-only by default, and that is a deliberate choice rather than an omission.
Atlas holds nothing overnight (§2.1), so a dividend never touches realised PnL —
it affects only the feature history, where a typical quarterly yield is a small
fraction of a single day's range. Including it would require carrying the prior
close through every adjustment call for an effect smaller than the tick size on
most names.

``include_dividends`` enables it for callers that have the reference close to
hand. If Atlas ever holds overnight, this default is wrong and must change with
the holding rule, not after it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Final

from atlas_core.domain.bar import Bar
from atlas_core.domain.corporate_action import ActionType, CorporateAction
from atlas_core.domain.money import Price

__all__ = [
    "AdjustmentFactors",
    "adjust_bar",
    "adjustment_factors",
    "knowable_actions",
]

ONE: Final = Decimal(1)


@dataclass(frozen=True, slots=True)
class AdjustmentFactors:
    """Multiplicative factors taking a raw bar to its as-of-adjusted form."""

    price: Decimal
    volume: Decimal

    @property
    def is_identity(self) -> bool:
        return self.price == ONE and self.volume == ONE


IDENTITY: Final = AdjustmentFactors(price=ONE, volume=ONE)


def knowable_actions(
    actions: Iterable[CorporateAction],
    *,
    knowledge_cutoff: datetime,
) -> list[CorporateAction]:
    """Filter to actions Atlas had actually learned about by ``knowledge_cutoff``.

    R-6.4.a. Separated from ``adjustment_factors`` so that callers which need the
    knowable set for other purposes — the Stage A pending-action check in rule
    A6, for instance — apply the identical filter rather than their own.
    """
    return [action for action in actions if action.knowledge_at <= knowledge_cutoff]


def adjustment_factors(
    actions: Sequence[CorporateAction],
    *,
    bar_date: date,
    as_of: date,
    knowledge_cutoff: datetime,
    include_dividends: bool = False,
    reference_close: Price | None = None,
) -> AdjustmentFactors:
    """Cumulative price and volume factors for a bar on ``bar_date``, seen at ``as_of``.

    ``as_of`` is the simulated vantage point — the date whose knowledge we are
    limited to. ``knowledge_cutoff`` is when we are asking, which for a backtest
    is the simulated clock and for research is usually "now".

    Passing ``as_of`` in the future relative to ``knowledge_cutoff`` is a
    programming error rather than a valid query, and raises.
    """
    if as_of < bar_date:
        raise ValueError(
            f"as_of {as_of} precedes bar_date {bar_date}: a bar cannot be viewed "
            "from before it existed"
        )
    if include_dividends and reference_close is None:
        raise ValueError("include_dividends requires reference_close (the pre-ex-date close)")

    price_factor = ONE
    volume_factor = ONE

    for action in knowable_actions(actions, knowledge_cutoff=knowledge_cutoff):
        # Strictly after the bar, at or before the vantage point. Both bounds matter;
        # see the module docstring.
        if not (bar_date < action.effective_at <= as_of):
            continue

        if action.action_type is ActionType.SPLIT:
            assert action.ratio is not None  # guaranteed by CorporateAction.__post_init__
            price_factor /= action.ratio
            volume_factor *= action.ratio
        elif action.action_type is ActionType.DIVIDEND and include_dividends:
            assert action.cash_amount is not None
            assert reference_close is not None
            if reference_close.amount <= 0:
                raise ValueError(f"reference_close must be positive, got {reference_close.amount}")
            price_factor *= ONE - (action.cash_amount.amount / reference_close.amount)

    return AdjustmentFactors(price=price_factor, volume=volume_factor)


def adjust_bar(
    bar: Bar,
    actions: Sequence[CorporateAction],
    *,
    as_of: date,
    knowledge_cutoff: datetime,
) -> Bar:
    """Return ``bar`` with prices and volume adjusted as of ``as_of``.

    The bar's own date is taken from its UTC timestamp. For US equities a session
    never straddles a UTC date boundary during regular hours, so this is safe;
    the overnight session Atlas does not trade (§2.2) would need the session date
    from the calendar instead.
    """
    factors = adjustment_factors(
        actions,
        bar_date=bar.ts.date(),
        as_of=as_of,
        knowledge_cutoff=knowledge_cutoff,
    )
    if factors.is_identity:
        return bar

    def scale(price: Price) -> Price:
        return Price(price.amount * factors.price)

    return Bar(
        symbol=bar.symbol,
        ts=bar.ts,
        open=scale(bar.open),
        high=scale(bar.high),
        low=scale(bar.low),
        close=scale(bar.close),
        # Truncate rather than round: a fractional share of volume is not a thing,
        # and rounding up would let an adjusted bar claim volume that never traded.
        volume=int(Decimal(bar.volume) * factors.volume),
        vwap=scale(bar.vwap) if bar.vwap is not None else None,
        trade_count=bar.trade_count,  # trade count is unaffected by a split
    )
