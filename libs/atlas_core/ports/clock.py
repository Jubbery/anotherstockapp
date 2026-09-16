"""The clock, as an input rather than an ambient fact."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

__all__ = ["ClockPort", "SystemClock"]


@runtime_checkable
class ClockPort(Protocol):
    """Source of the current time.

    Decision code takes this rather than calling ``datetime.now()`` so the
    backtester can drive the same code through simulated time (R-8.2.a) and the
    risk governor can remain a pure function of its arguments (R-12.1.a).
    """

    def now(self) -> datetime:
        """Return the current time, timezone-aware, UTC (R-5.4.a)."""
        ...


class SystemClock:
    """The production clock.

    R-10.8 note: the engine compares this against the broker's clock at startup
    and hourly, and halts on skew beyond the threshold. Machine time is not
    assumed to be correct, it is checked.
    """

    __slots__ = ()

    def now(self) -> datetime:
        from atlas_core.domain.time import utc_now

        return utc_now()
