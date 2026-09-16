"""Session arithmetic.

R-5.4.c: session boundaries come from the exchange calendar, never from
hardcoded 09:30/16:00 constants. This module therefore contains **no** session
times of its own — it is arithmetic over calendar rows supplied by
``ReferenceDataPort``.

The reason is R-12.4.d. Atlas force-flattens every position before the close
(R-12.4.b). On a half-day — the day after US Thanksgiving, Christmas Eve, 3 July
— the close is 13:00 ET, not 16:00. An engine that flattens at "15:55" on such a
day has already held a position through the close for nearly three hours, and
§2.1 says Atlas never holds overnight. The offsets below are measured *backwards
from the real close* for exactly that reason.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from atlas_core.domain.time import ensure_utc

__all__ = ["MarketCalendar", "Session", "SessionTimes", "UnknownSessionError"]


class UnknownSessionError(LookupError):
    """The calendar has nothing to say about this date.

    Raised rather than defaulted. A guessed session boundary is the failure
    R-5.4.c exists to prevent, and an engine that cannot establish when the
    market closes must not be trading.
    """


@dataclass(frozen=True, slots=True)
class Session:
    """One row of the exchange calendar."""

    session_date: date
    is_trading_day: bool
    open_at: datetime | None = None
    close_at: datetime | None = None
    is_half_day: bool = False

    def __post_init__(self) -> None:
        if self.is_trading_day:
            if self.open_at is None or self.close_at is None:
                raise ValueError(f"{self.session_date}: a trading day needs open and close times")
            object.__setattr__(self, "open_at", ensure_utc(self.open_at, field="open_at"))
            object.__setattr__(self, "close_at", ensure_utc(self.close_at, field="close_at"))
            if self.close_at <= self.open_at:
                raise ValueError(f"{self.session_date}: close {self.close_at} is not after open")
        elif self.open_at is not None or self.close_at is not None:
            raise ValueError(f"{self.session_date}: a non-trading day must have no session times")

    @property
    def duration(self) -> timedelta:
        if not self.is_trading_day:
            return timedelta(0)
        assert self.open_at is not None and self.close_at is not None
        return self.close_at - self.open_at


@dataclass(frozen=True, slots=True)
class SessionTimes:
    """The moments the engine's state machine turns on, for one session.

    All derived from the real close, so a half-day shifts every one of them.
    """

    session_date: date
    open_at: datetime
    close_at: datetime
    entry_window_opens_at: datetime
    no_new_entries_after: datetime
    force_flatten_at: datetime
    is_half_day: bool


@dataclass(frozen=True, slots=True)
class MarketCalendar:
    """Calendar rows, indexed by date.

    Immutable, and built from data the ingest recorded. It answers questions; it
    does not invent answers.
    """

    sessions: Mapping[date, Session]

    @classmethod
    def build(cls, sessions: Iterable[Session]) -> MarketCalendar:
        indexed: dict[date, Session] = {}
        for session in sessions:
            if session.session_date in indexed:
                raise ValueError(f"duplicate calendar row for {session.session_date}")
            indexed[session.session_date] = session
        return cls(sessions=indexed)

    def session(self, day: date) -> Session:
        try:
            return self.sessions[day]
        except KeyError as exc:
            raise UnknownSessionError(
                f"No calendar row for {day}. Refusing to guess session boundaries " f"(R-5.4.c)."
            ) from exc

    def is_trading_day(self, day: date) -> bool:
        return self.session(day).is_trading_day

    def trading_days(self, start: date, end: date) -> tuple[date, ...]:
        """Trading days in ``[start, end]``, in order.

        Raises if any date in the range is missing, rather than skipping it: a
        gap in the calendar would silently shorten a lookback window, and a
        20-session average computed over 18 sessions is wrong without being
        obviously wrong.
        """
        if end < start:
            raise ValueError(f"end {end} precedes start {start}")
        days: list[date] = []
        cursor = start
        while cursor <= end:
            if self.session(cursor).is_trading_day:
                days.append(cursor)
            cursor += timedelta(days=1)
        return tuple(days)

    def previous_trading_day(self, day: date, *, lookback_limit: int = 10) -> date:
        """The most recent trading day strictly before ``day``.

        ``lookback_limit`` bounds the walk so a sparse calendar raises instead of
        looping. Ten days covers the longest US market closure in normal
        operation; a longer gap is an event Atlas should stop for anyway.
        """
        cursor = day - timedelta(days=1)
        for _ in range(lookback_limit):
            if self.session(cursor).is_trading_day:
                return cursor
            cursor -= timedelta(days=1)
        raise UnknownSessionError(f"No trading day in the {lookback_limit} days before {day}.")

    def session_times(
        self,
        day: date,
        *,
        opening_range: timedelta,
        no_new_entries_before_close: timedelta,
        flatten_before_close: timedelta,
    ) -> SessionTimes:
        """Derive the engine's decision times for ``day``.

        Every offset is measured **backwards from the close**, which is what makes
        half-days correct without a special case: on a 13:00 ET close the flatten
        lands at 12:55, not 15:55.

        The opening-range offset is measured forwards from the open, since that is
        what it describes.
        """
        session = self.session(day)
        if not session.is_trading_day:
            raise UnknownSessionError(f"{day} is not a trading day; it has no session times")
        assert session.open_at is not None and session.close_at is not None

        if flatten_before_close <= timedelta(0):
            raise ValueError(
                "flatten_before_close must be positive; flattening at or after "
                "the close is holding overnight"
            )
        if no_new_entries_before_close < flatten_before_close:
            raise ValueError(
                "no_new_entries_before_close must be at least flatten_before_close, "
                "or the engine could open a position it must immediately flatten"
            )

        force_flatten_at = session.close_at - flatten_before_close
        no_new_entries_after = session.close_at - no_new_entries_before_close
        entry_window_opens_at = session.open_at + opening_range

        if entry_window_opens_at >= no_new_entries_after:
            # A session too short to contain the configured windows. Real on a
            # half-day with generous offsets, and the engine must be told rather
            # than silently trading a zero-length window.
            raise ValueError(
                f"{day}: the entry window is empty "
                f"(opens {entry_window_opens_at}, closes {no_new_entries_after}). "
                f"Session is {session.duration}; check the offsets against half-days."
            )

        return SessionTimes(
            session_date=day,
            open_at=session.open_at,
            close_at=session.close_at,
            entry_window_opens_at=entry_window_opens_at,
            no_new_entries_after=no_new_entries_after,
            force_flatten_at=force_flatten_at,
            is_half_day=session.is_half_day,
        )
