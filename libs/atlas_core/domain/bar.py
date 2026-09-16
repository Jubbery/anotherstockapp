"""OHLCV bars, and the timestamp convention that governs every feature window.

**R-6.4.g — the convention, stated once.** A bar's timestamp is its **open**:
a bar stamped ``14:31:00Z`` covers ``[14:31:00, 14:32:00)``. It therefore
contains information from the future relative to its own timestamp, which is why
a decision taken *at* 14:31 may use the bar stamped **14:30** as its most recent
complete bar, and not the one stamped 14:31.

This is the most common lookahead bug in intraday systems and it is invisible in
results other than by making them better. ``last_complete_bar_open`` below is the
only sanctioned way to answer "which bar may I use right now"; computing it
inline at a call site is how the off-by-one gets reintroduced.

The convention is an **assumption about the vendor** until the proof of concept
confirms it (``docs/research/2026-09-16-alpaca-mcp-poc.md``, step 3.2). If it
turns out Alpaca stamps bars with their close, ``BAR_TIMESTAMP_IS_OPEN`` flips
and the tests below encode what must change with it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Final

from atlas_core.domain.money import Price
from atlas_core.domain.time import ensure_utc

__all__ = [
    "BAR_TIMESTAMP_IS_OPEN",
    "Bar",
    "BarValidationError",
    "last_complete_bar_open",
]

# R-6.4.g. Flipping this is a breaking change to every feature and label; it
# exists as a named constant so the assumption is greppable rather than implicit.
BAR_TIMESTAMP_IS_OPEN: Final = True


class BarValidationError(ValueError):
    """A bar violated an invariant that ingest must never let through (R-6.6.b)."""


@dataclass(frozen=True, slots=True)
class Bar:
    """One OHLCV bar. Prices are raw and unadjusted (R-6.4.d).

    Adjustment is applied at read time, as of a date, by
    ``atlas_core.pit.adjustment``. Storing adjusted prices would mean every split
    silently rewrites history, so that a model trained on Tuesday sees a
    different past than the same model trained on Monday.
    """

    symbol: str
    ts: datetime
    open: Price
    high: Price
    low: Price
    close: Price
    volume: int
    vwap: Price | None = None
    trade_count: int | None = None

    def __post_init__(self) -> None:
        # R-6.6.b: these are rejects at ingest, not warnings. A bar that violates
        # them is a vendor bug or a parsing bug, and either way the feature
        # computed over it is wrong in a way nothing downstream would notice.
        object.__setattr__(self, "ts", ensure_utc(self.ts, field=f"{self.symbol} bar ts"))

        if not self.symbol:
            raise BarValidationError("Bar requires a symbol")
        if self.volume < 0:
            raise BarValidationError(f"{self.symbol} {self.ts}: negative volume {self.volume}")
        if self.trade_count is not None and self.trade_count < 0:
            raise BarValidationError(f"{self.symbol} {self.ts}: negative trade_count")
        if self.low > self.high:
            raise BarValidationError(
                f"{self.symbol} {self.ts}: low {self.low.amount} > high {self.high.amount}"
            )
        for name, price in (("open", self.open), ("close", self.close)):
            if price < self.low or price > self.high:
                raise BarValidationError(
                    f"{self.symbol} {self.ts}: {name} {price.amount} outside "
                    f"[{self.low.amount}, {self.high.amount}]"
                )

    @property
    def range_pct(self) -> Decimal:
        """(high - low) / close. Zero-close bars cannot occur; equities trade above 0."""
        return (self.high.amount - self.low.amount) / self.close.amount

    @property
    def dollar_volume(self) -> Decimal:
        """Approximate traded notional, using VWAP when available.

        Stage A rule A8 ranks on this. VWAP is materially more accurate than
        close x volume on a trending bar, so prefer it when the vendor supplies it.
        """
        reference = self.vwap if self.vwap is not None else self.close
        return reference.amount * Decimal(self.volume)


def last_complete_bar_open(
    now: datetime,
    *,
    bar_interval: timedelta,
    session_open: datetime,
) -> datetime | None:
    """Timestamp of the newest bar that is fully in the past at ``now``.

    R-6.4.g. Returns the bar's **open** timestamp, matching storage. Returns
    ``None`` before the first bar of the session has completed.

    The arithmetic is deliberately strict: a bar is usable only once its whole
    interval has elapsed. At exactly 14:32:00 the bar stamped 14:31 has just
    closed and is usable; at 14:31:59.999 it is not, because its last trade has
    not happened yet. Taking the bar "currently forming" is lookahead.
    """
    now = ensure_utc(now, field="now")
    session_open = ensure_utc(session_open, field="session_open")
    if bar_interval <= timedelta(0):
        raise ValueError(f"bar_interval must be positive, got {bar_interval}")

    elapsed = now - session_open
    if elapsed < bar_interval:
        return None

    completed = int(elapsed // bar_interval)
    return session_open + (completed - 1) * bar_interval
