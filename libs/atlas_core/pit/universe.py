"""Point-in-time universe construction.

R-6.4.b: the tradeable universe is snapshotted daily, **including symbols that
later delist**, and a backtest for date *D* builds its universe from the snapshot
taken on *D* — never from today's asset list.

Using today's list is survivorship bias, and it is the most flattering error in
quantitative finance: every company that went to zero is quietly absent, so a
strategy is measured only on the names that made it. It does not look like a bug.
It looks like skill.

R-6.4.c: delisted symbols are retained with ``delisted_at`` set, and their bars
are kept. Deleting them reintroduces the bias through the back door.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

__all__ = ["UniverseEntry", "UniverseSnapshot", "SurvivorshipError"]


class SurvivorshipError(RuntimeError):
    """Raised when a universe is built from something other than a snapshot."""


@dataclass(frozen=True, slots=True)
class UniverseEntry:
    """One symbol's tradeable status on one date."""

    symbol: str
    tradable: bool
    shortable: bool
    easy_to_borrow: bool
    marginable: bool
    # Set when the symbol had already delisted as of the snapshot date. Kept so
    # that a snapshot is self-describing rather than needing a join to interpret.
    delisted_at: date | None = None

    @property
    def is_eligible(self) -> bool:
        """Stage A tier-1 eligibility, as far as the asset master can answer it."""
        return self.tradable and self.delisted_at is None


@dataclass(frozen=True, slots=True)
class UniverseSnapshot:
    """The tradeable universe as it stood on ``as_of``.

    Immutable by construction: a snapshot that can be edited after the fact is a
    snapshot that can acquire hindsight.
    """

    as_of: date
    entries: tuple[UniverseEntry, ...]

    @classmethod
    def build(cls, as_of: date, entries: Iterable[UniverseEntry]) -> UniverseSnapshot:
        ordered = tuple(sorted(entries, key=lambda entry: entry.symbol))
        seen = {entry.symbol for entry in ordered}
        if len(seen) != len(ordered):
            raise ValueError(f"duplicate symbols in universe snapshot for {as_of}")
        return cls(as_of=as_of, entries=ordered)

    def __len__(self) -> int:
        return len(self.entries)

    def symbols(self) -> tuple[str, ...]:
        return tuple(entry.symbol for entry in self.entries)

    def eligible(self) -> tuple[UniverseEntry, ...]:
        """Entries that could actually be traded on ``as_of``."""
        return tuple(entry for entry in self.entries if entry.is_eligible)

    def contains(self, symbol: str) -> bool:
        return any(entry.symbol == symbol for entry in self.entries)

    def delisted(self) -> tuple[UniverseEntry, ...]:
        """Symbols in this snapshot that had already delisted.

        Present deliberately. A snapshot with none of these, across a multi-year
        backtest, is the signature of a survivorship-biased universe, and
        ``assert_retains_delistings`` below turns that observation into a test.
        """
        return tuple(entry for entry in self.entries if entry.delisted_at is not None)


def assert_retains_delistings(
    snapshots: Iterable[UniverseSnapshot],
    *,
    minimum: int = 1,
) -> None:
    """Fail loudly if a run of snapshots contains no delisted symbols at all.

    US equities delist constantly — mergers, acquisitions, bankruptcies,
    compliance failures. A multi-month span of snapshots with zero delistings
    means the ingest is rebuilding history from today's asset list rather than
    recording it as it stood, and every backtest built on it is overstated.

    This is a cheap smoke alarm, not a proof. Phase 1's acceptance criterion
    still requires naming specific symbols that were tradeable in 2023 and are
    not now, and showing them present (§20.2).
    """
    found = sum(len(snapshot.delisted()) for snapshot in snapshots)
    if found < minimum:
        raise SurvivorshipError(
            f"{found} delisted symbols across the given snapshots (expected at least "
            f"{minimum}). A universe with no delistings is the signature of "
            f"survivorship bias -- see MASTER_SPEC R-6.4.b."
        )
