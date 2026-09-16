"""Point-in-time ticker resolution.

R-6.4.h. A ticker names a company only for a stretch of time. Two failure modes,
pointing in opposite directions, and neither raises:

* A **ticker change** splits one company across two keys. FB became META in
  June 2022; keyed by symbol, a 60-day window spanning that date sees two
  securities with thirty days of history each, and every momentum and volatility
  feature over them is wrong.
* A **ticker reuse** joins two companies under one key. A delisted ticker
  returns to the pool and is reassigned; keyed by symbol, the dead company's
  prices and the new company's form one series, with a handover discontinuity
  that looks exactly like a tradeable gap.

The second is the dangerous one, because it manufactures an *attractive*
feature -- the signature of the bug class §9.1 exists to catch.

The database enforces non-overlap with an exclusion constraint (migration 0005).
This module is the read path, and it is deliberately strict in the same way:
unresolvable is an error, never a guess.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime

from atlas_core.domain.time import ensure_utc

__all__ = [
    "AmbiguousSymbolError",
    "InstrumentId",
    "SymbolMapping",
    "SymbolResolver",
    "UnknownSymbolError",
]

type InstrumentId = int


class UnknownSymbolError(LookupError):
    """No instrument wore this ticker on this date, as far as we knew.

    Raised rather than returning ``None`` so that a caller cannot drift into
    treating "unknown" as "probably the current one". Between a delisting and a
    reassignment the honest answer is that nobody was quoting it.
    """


class AmbiguousSymbolError(RuntimeError):
    """Two instruments claim this ticker on this date.

    The database refuses to store this (migration 0005), so reaching it means
    the mappings came from somewhere that did not go through those constraints.
    Raised rather than resolved, because resolving would mean picking one
    silently -- and a silent pick here is a whole company's history attached to
    the wrong bars.
    """


@dataclass(frozen=True, slots=True)
class SymbolMapping:
    """One ticker's claim on one instrument, over a half-open date range.

    ``valid_until`` of ``None`` means "still current". Half-open
    ``[valid_from, valid_until)`` matters at the changeover: on the day the
    rename takes effect the new ticker is live and the old one is not. An
    inclusive upper bound would make both resolve on that day.
    """

    symbol: str
    instrument_id: InstrumentId
    valid_from: date
    valid_until: date | None
    knowledge_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "knowledge_at", ensure_utc(self.knowledge_at, field="knowledge_at")
        )
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValueError(
                f"{self.symbol}: valid_until {self.valid_until} must be after "
                f"valid_from {self.valid_from}"
            )

    def covers(self, as_of: date) -> bool:
        return self.valid_from <= as_of and (self.valid_until is None or as_of < self.valid_until)

    def was_knowable_at(self, cutoff: datetime) -> bool:
        """R-6.4.a. A rename is announced before it takes effect."""
        return self.knowledge_at <= cutoff


@dataclass(frozen=True, slots=True)
class SymbolResolver:
    """Resolves tickers to instruments, as of a date.

    Built from mappings loaded out of ``symbol_mappings``. Immutable: a resolver
    that can be extended mid-backtest is one that can acquire hindsight.
    """

    mappings: tuple[SymbolMapping, ...]

    @classmethod
    def build(cls, mappings: Iterable[SymbolMapping]) -> SymbolResolver:
        return cls(mappings=tuple(mappings))

    def resolve(
        self,
        symbol: str,
        *,
        as_of: date,
        knowledge_cutoff: datetime,
    ) -> InstrumentId:
        """Which instrument wore ``symbol`` on ``as_of``, as known at the cutoff."""
        candidates = [
            mapping
            for mapping in self.mappings
            if mapping.symbol == symbol
            and mapping.covers(as_of)
            and mapping.was_knowable_at(knowledge_cutoff)
        ]
        if not candidates:
            raise UnknownSymbolError(
                f"No instrument wore {symbol!r} on {as_of} (as known at "
                f"{knowledge_cutoff.isoformat()}). Refusing to fall back to the current "
                f"mapping -- that is how a reused ticker joins two companies' histories "
                f"(R-6.4.h)."
            )
        instruments = {mapping.instrument_id for mapping in candidates}
        if len(instruments) > 1:
            raise AmbiguousSymbolError(
                f"{symbol!r} on {as_of} resolves to {sorted(instruments)}. Overlapping "
                f"mappings should have been refused at write time (migration 0005)."
            )
        return candidates[0].instrument_id

    def symbol_for(
        self,
        instrument_id: InstrumentId,
        *,
        as_of: date,
        knowledge_cutoff: datetime,
    ) -> str:
        """The reverse: what was this instrument called on ``as_of``?

        Needed whenever Atlas talks to the outside world about a past date --
        a research note, a report, a chart axis. The broker only knows tickers.
        """
        candidates = [
            mapping
            for mapping in self.mappings
            if mapping.instrument_id == instrument_id
            and mapping.covers(as_of)
            and mapping.was_knowable_at(knowledge_cutoff)
        ]
        if not candidates:
            raise UnknownSymbolError(f"Instrument {instrument_id} had no ticker on {as_of}.")
        symbols = {mapping.symbol for mapping in candidates}
        if len(symbols) > 1:
            raise AmbiguousSymbolError(
                f"Instrument {instrument_id} wore {sorted(symbols)} on {as_of}."
            )
        return candidates[0].symbol

    def history(self, instrument_id: InstrumentId) -> tuple[SymbolMapping, ...]:
        """Every ticker this instrument has worn, oldest first."""
        return tuple(
            sorted(
                (m for m in self.mappings if m.instrument_id == instrument_id),
                key=lambda mapping: mapping.valid_from,
            )
        )
