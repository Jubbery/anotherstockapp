"""A clock that only moves when told to."""

from __future__ import annotations

from datetime import datetime, timedelta

from atlas_core.domain.time import ensure_utc

__all__ = ["FrozenClock"]


class FrozenClock:
    """A ``ClockPort`` whose time advances only by explicit call.

    Used by unit tests and, in Phase 3, by the backtester's event loop. Tests that
    read the wall clock are non-deterministic, and a flaky test in a
    safety-critical suite gets fixed rather than retried (R-18.2.a).
    """

    __slots__ = ("_now",)

    def __init__(self, now: datetime) -> None:
        self._now = ensure_utc(now, field="FrozenClock start")

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        if delta < timedelta(0):
            raise ValueError("Time does not run backwards; use a new FrozenClock.")
        self._now += delta
