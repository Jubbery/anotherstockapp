"""Timezone-aware UTC time.

R-5.4.a: naive datetimes do not cross function boundaries. R-5.4.b:
``America/New_York`` appears only at the display layer. R-5.4.c: session
boundaries come from the exchange calendar, never from constants in this module
-- there is deliberately no ``MARKET_OPEN = time(9, 30)`` here, because half-days
exist and a hardcoded close is a position held overnight.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final
from zoneinfo import ZoneInfo

__all__ = ["NEW_YORK", "ensure_utc", "format_for_display", "utc_now"]

# Display only (R-5.4.b). Nothing in storage or in a domain object uses this.
NEW_YORK: Final = ZoneInfo("America/New_York")


def utc_now() -> datetime:
    """Current time, timezone-aware, UTC.

    Production decision code does not call this -- it takes the clock as an input
    via ``ClockPort`` so the backtester can drive it (R-4.3.b) and the risk
    governor can stay pure (R-12.1.a). This exists for adapters and logging.
    """
    return datetime.now(UTC)


def ensure_utc(value: datetime, *, field: str = "timestamp") -> datetime:
    """Return ``value`` in UTC, rejecting naive datetimes.

    A naive datetime is not "probably UTC" -- it is an unknown offset, and the
    difference shows up as bars attributed to the wrong minute (R-6.4.g).
    """
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(
            f"{field} is a naive datetime ({value!r}). Timestamps must be "
            "timezone-aware UTC -- see MASTER_SPEC R-5.4.a."
        )
    return value.astimezone(UTC)


def format_for_display(value: datetime) -> str:
    """Render in New York time, always labelled (R-5.4.b, R-15.4.a).

    A time shown without its zone is a defect, so the label is not optional here.
    """
    return ensure_utc(value).astimezone(NEW_YORK).strftime("%Y-%m-%d %H:%M:%S %Z")
