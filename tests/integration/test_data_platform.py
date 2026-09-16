"""Data platform schema: §6 invariants enforced by the database.

The database is the last line of defence for these. Ingest validates with
Pydantic (R-6.6.a) and the domain types validate again (R-6.6.b), but a bad row
that reaches Postgres through a path nobody anticipated must still be refused --
a feature computed over an impossible bar is wrong in a way nothing downstream
notices.

Set ``ATLAS_TEST_DATABASE_URL`` to run.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from pathlib import Path

import asyncpg
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = sorted((REPO_ROOT / "db" / "migrations").glob("*.sql"))
DATABASE_URL = os.environ.get("ATLAS_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="ATLAS_TEST_DATABASE_URL is not set; no database to migrate"
)

BAR = (
    "INSERT INTO bars_daily (instrument_id, symbol_as_reported, session_date, "
    "open, high, low, close, volume, data_feed) "
    "VALUES (1, 'AAPL', $1, $2, $3, $4, $5, $6, 'sip')"
)


@pytest.fixture
async def db() -> AsyncIterator[asyncpg.Connection]:
    assert DATABASE_URL is not None
    conn: asyncpg.Connection = await asyncpg.connect(DATABASE_URL)
    await conn.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
    for path in MIGRATIONS:
        await conn.execute(path.read_text(encoding="utf-8"))
    await conn.execute(
        "INSERT INTO instruments (instrument_id, primary_symbol, name) "
        "OVERRIDING SYSTEM VALUE VALUES (1, 'AAPL', 'Apple')"
    )
    try:
        yield conn
    finally:
        await conn.close()


# ------------------------------------------------------------------- bars


async def test_a_sane_bar_is_accepted_and_routed_to_its_partition(
    db: asyncpg.Connection,
) -> None:
    await db.execute(BAR, date(2026, 9, 15), 100, 101, 99, 100.5, 1_000_000)
    partition = await db.fetchval("SELECT tableoid::regclass::text FROM bars_daily")
    assert partition == "bars_daily_2026"


@pytest.mark.parametrize(
    ("label", "o", "h", "low", "c", "v"),
    [
        ("low above high", 100, 99, 101, 100, 1_000),
        ("close above high", 100, 101, 99, 150, 1_000),
        ("close below low", 100, 101, 99, 50, 1_000),
        ("open outside range", 150, 101, 99, 100, 1_000),
        ("negative volume", 100, 101, 99, 100, -5),
        ("zero low", 100, 101, 0, 100, 1_000),
    ],
)
async def test_impossible_bars_are_refused(
    db: asyncpg.Connection, label: str, o: int, h: int, low: int, c: int, v: int
) -> None:
    """R-6.6.b. Each of these is a vendor or parsing bug, not a market event."""
    with pytest.raises(asyncpg.PostgresError, match="bars_daily_sane"):
        await db.execute(BAR, date(2026, 9, 14), o, h, low, c, v)


async def test_a_bar_outside_every_partition_fails_loudly(db: asyncpg.Connection) -> None:
    """No default partition, deliberately.

    A default would silently absorb a session_date of 2202 -- a parsing bug --
    and the row would sit there looking valid. Failing the insert surfaces it.
    """
    with pytest.raises(asyncpg.PostgresError, match="no partition of relation"):
        await db.execute(BAR, date(2202, 9, 14), 100, 101, 99, 100, 1_000)


async def test_zero_volume_bars_are_allowed(db: asyncpg.Connection) -> None:
    """A session with no trades is real. Dropping it leaves a silent hole."""
    await db.execute(BAR, date(2026, 9, 11), 100, 100, 100, 100, 0)
    assert await db.fetchval("SELECT count(*) FROM bars_daily") == 1


async def test_minute_bars_must_sit_on_the_minute_grid(db: asyncpg.Connection) -> None:
    """R-6.4.g. An unaligned timestamp means the vendor's convention is not ours."""
    minute_insert = (
        "INSERT INTO bars_minute_hot (instrument_id, symbol_as_reported, ts, "
        "open, high, low, close, volume, data_feed) "
        "VALUES (1, 'AAPL', $1::timestamptz, 100, 101, 99, 100, 500, 'sip')"
    )
    with pytest.raises(asyncpg.PostgresError, match="bars_minute_hot_aligned"):
        await db.execute(minute_insert, datetime(2026, 9, 16, 14, 31, 30, tzinfo=UTC))

    await db.execute(minute_insert, datetime(2026, 9, 16, 14, 31, tzinfo=UTC))
    assert await db.fetchval("SELECT count(*) FROM bars_minute_hot") == 1


# --------------------------------------------------------- corporate actions


async def test_a_split_without_a_ratio_is_refused(db: asyncpg.Connection) -> None:
    """A null ratio would make the adjustment factor undefined."""
    with pytest.raises(asyncpg.PostgresError, match="split_has_ratio"):
        await db.execute(
            "INSERT INTO corporate_actions (symbol, action_type, effective_at, knowledge_at, raw) "
            "VALUES ('AAPL', 'split', '2026-06-10', now(), '{}')"
        )


async def test_a_split_with_a_zero_ratio_is_refused(db: asyncpg.Connection) -> None:
    """Ratio zero divides prices by zero; ratio negative flips them."""
    with pytest.raises(asyncpg.PostgresError, match="split_has_ratio"):
        await db.execute(
            "INSERT INTO corporate_actions "
            "(symbol, action_type, effective_at, knowledge_at, ratio, raw) "
            "VALUES ('AAPL', 'split', '2026-06-10', now(), 0, '{}')"
        )


async def test_knowledge_time_is_independent_of_effective_time(
    db: asyncpg.Connection,
) -> None:
    """R-6.4.a. The same action can be learned twice, at different times.

    A vendor backfill often delivers a corporate action days after its ex-date.
    Both rows must coexist so a backtest can ask what we knew *then*.
    """
    insert = (
        "INSERT INTO corporate_actions "
        "(symbol, action_type, effective_at, knowledge_at, ratio, raw) "
        "VALUES ('AAPL', 'split', '2026-06-10', $1::timestamptz, 10, '{}')"
    )
    await db.execute(insert, datetime(2026, 5, 22, 20, 5, tzinfo=UTC))
    await db.execute(insert, datetime(2026, 6, 15, 3, 0, tzinfo=UTC))

    knowable_early = await db.fetchval(
        "SELECT count(*) FROM corporate_actions WHERE knowledge_at <= '2026-06-01'"
    )
    assert knowable_early == 1, "a backtest on 2026-06-01 knew of exactly one announcement"


# ------------------------------------------------------------------ calendar


async def test_a_trading_day_must_have_both_open_and_close(db: asyncpg.Connection) -> None:
    """R-5.4.c. A half-day with a missing close is a position held overnight."""
    with pytest.raises(asyncpg.PostgresError, match="times_paired"):
        await db.execute(
            "INSERT INTO market_calendar (session_date, is_trading_day, open_at, is_half_day) "
            "VALUES ('2026-11-27', true, '2026-11-27 14:30+00', true)"
        )


async def test_half_days_are_representable(db: asyncpg.Connection) -> None:
    """The day after US Thanksgiving closes at 13:00 ET."""
    await db.execute(
        "INSERT INTO market_calendar "
        "(session_date, is_trading_day, open_at, close_at, is_half_day) "
        "VALUES ('2026-11-27', true, '2026-11-27 14:30+00', '2026-11-27 18:00+00', true)"
    )
    close = await db.fetchval("SELECT close_at FROM market_calendar WHERE is_half_day")
    assert close.hour == 18  # 13:00 ET


async def test_a_non_trading_day_must_not_have_session_times(db: asyncpg.Connection) -> None:
    with pytest.raises(asyncpg.PostgresError, match="times_paired"):
        await db.execute(
            "INSERT INTO market_calendar "
            "(session_date, is_trading_day, open_at, close_at) "
            "VALUES ('2026-12-25', false, '2026-12-25 14:30+00', '2026-12-25 21:00+00')"
        )


# ------------------------------------------------------------------ universe


async def test_a_delisted_symbol_stays_in_its_historical_snapshot(
    db: asyncpg.Connection,
) -> None:
    """R-6.4.b / R-6.4.c -- the survivorship guarantee, at the storage layer."""
    await db.execute(
        "INSERT INTO instruments (instrument_id, primary_symbol, name) "
        "OVERRIDING SYSTEM VALUE VALUES (2, 'SIVB', 'SVB Financial')"
    )
    await db.execute(
        "INSERT INTO universe_snapshots "
        "(as_of, instrument_id, symbol, tradable, shortable, easy_to_borrow, marginable, "
        "delisted_at) VALUES "
        "('2023-06-01', 2, 'SIVB', true, true, true, true, NULL), "
        "('2024-01-02', 2, 'SIVB', false, false, false, false, '2023-05-01')"
    )
    rows = await db.fetch(
        "SELECT as_of, tradable, delisted_at FROM universe_snapshots "
        "WHERE symbol = 'SIVB' ORDER BY as_of"
    )
    assert rows[0]["tradable"] is True and rows[0]["delisted_at"] is None
    assert rows[1]["tradable"] is False and rows[1]["delisted_at"] is not None


async def test_instruments_are_never_deleted_only_marked(db: asyncpg.Connection) -> None:
    """R-6.4.c. A snapshot references the instrument, so a delete must cascade.

    The foreign key makes removing an instrument with history impossible without
    deliberately destroying that history first, which is the friction we want.
    """
    await db.execute(
        "INSERT INTO instruments (instrument_id, primary_symbol) "
        "OVERRIDING SYSTEM VALUE VALUES (2, 'SIVB')"
    )
    await db.execute(
        "INSERT INTO universe_snapshots "
        "(as_of, instrument_id, symbol, tradable, shortable, easy_to_borrow, marginable) "
        "VALUES ('2023-06-01', 2, 'SIVB', true, true, true, true)"
    )
    with pytest.raises(asyncpg.PostgresError, match="violates foreign key"):
        await db.execute("DELETE FROM instruments WHERE instrument_id = 2")


# ------------------------------------------------------------------- ingest


async def test_rejects_keep_their_raw_payload(db: asyncpg.Connection) -> None:
    """R-6.6.a. A rising reject rate is a leading indicator of a vendor change."""
    run_id = await db.fetchval(
        "INSERT INTO ingest_runs (kind, data_feed) VALUES ('nightly', 'sip') RETURNING id"
    )
    await db.execute(
        "INSERT INTO ingest_rejects (ingest_run_id, symbol, reason, raw) "
        "VALUES ($1, 'AAPL', 'low > high', '{\"h\": 99, \"l\": 101}')",
        run_id,
    )
    raw = await db.fetchval("SELECT raw FROM ingest_rejects")
    assert "101" in raw


async def test_data_quality_result_is_constrained(db: asyncpg.Connection) -> None:
    """R-6.7.a. 'block' is a real value with a real consequence, not free text."""
    with pytest.raises(asyncpg.PostgresError, match="data_quality_result_known"):
        await db.execute(
            "INSERT INTO data_quality_runs (as_of, result, checks) "
            "VALUES ('2026-09-16', 'probably-fine', '{}')"
        )
