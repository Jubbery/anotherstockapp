"""R-6.4.h — a ticker is not an identity.

Two failure modes, pointing in opposite directions, neither of which raises:

* **Ticker change** splits one company across two keys. FB became META in June
  2022; keyed by symbol, a 60-day window spanning that date sees two securities
  with 30 days of history each.
* **Ticker reuse** joins two companies under one key. A delisted ticker returns
  to the pool and is reassigned; keyed by symbol, the dead company's prices and
  the new company's form one series with a handover discontinuity that looks
  exactly like a tradeable gap.

The second is the dangerous one: it manufactures an attractive feature.
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

RESOLVE = """
    SELECT m.instrument_id, i.name
    FROM symbol_mappings m
    JOIN instruments i USING (instrument_id)
    WHERE m.symbol = $1
      AND daterange(m.valid_from, m.valid_until, '[)') @> $2::date
      AND m.knowledge_at <= $3::timestamptz
"""


@pytest.fixture
async def db() -> AsyncIterator[asyncpg.Connection]:
    assert DATABASE_URL is not None
    conn: asyncpg.Connection = await asyncpg.connect(DATABASE_URL)
    await conn.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
    for path in MIGRATIONS:
        await conn.execute(path.read_text(encoding="utf-8"))
    try:
        yield conn
    finally:
        await conn.close()


async def new_instrument(db: asyncpg.Connection, symbol: str, name: str, **kw: object) -> int:
    row: int = await db.fetchval(
        "INSERT INTO instruments (primary_symbol, name, delisted_at) "
        "VALUES ($1, $2, $3) RETURNING instrument_id",
        symbol,
        name,
        kw.get("delisted_at"),
    )
    return row


async def map_symbol(
    db: asyncpg.Connection,
    symbol: str,
    instrument_id: int,
    valid_from: date,
    valid_until: date | None,
    knowledge_at: datetime | None = None,
) -> None:
    await db.execute(
        "INSERT INTO symbol_mappings "
        "(symbol, instrument_id, valid_from, valid_until, knowledge_at) "
        "VALUES ($1, $2, $3, $4, $5)",
        symbol,
        instrument_id,
        valid_from,
        valid_until,
        knowledge_at or datetime(valid_from.year, valid_from.month, valid_from.day, tzinfo=UTC),
    )


NOW = datetime(2026, 9, 16, tzinfo=UTC)


# ------------------------------------------------------- ticker change


async def test_a_renamed_company_keeps_one_identity(db: asyncpg.Connection) -> None:
    """FB -> META. One instrument, two tickers, one continuous history."""
    meta = await new_instrument(db, "META", "Meta Platforms")
    await map_symbol(db, "FB", meta, date(2012, 5, 18), date(2022, 6, 9))
    await map_symbol(db, "META", meta, date(2022, 6, 9), None, datetime(2022, 6, 1, tzinfo=UTC))

    before = await db.fetchrow(RESOLVE, "FB", date(2020, 1, 2), NOW)
    after = await db.fetchrow(RESOLVE, "META", date(2024, 1, 2), NOW)

    assert (
        before["instrument_id"] == after["instrument_id"] == meta
    ), "a 60-day feature window spanning the rename must see one security, not two"


async def test_the_new_ticker_does_not_resolve_before_it_existed(
    db: asyncpg.Connection,
) -> None:
    """Asking for META in 2020 is asking about a ticker nobody was quoting."""
    meta = await new_instrument(db, "META", "Meta Platforms")
    await map_symbol(db, "FB", meta, date(2012, 5, 18), date(2022, 6, 9))
    await map_symbol(db, "META", meta, date(2022, 6, 9), None, datetime(2022, 6, 1, tzinfo=UTC))

    assert await db.fetchrow(RESOLVE, "META", date(2020, 1, 2), NOW) is None


async def test_the_old_ticker_does_not_resolve_after_the_change(
    db: asyncpg.Connection,
) -> None:
    meta = await new_instrument(db, "META", "Meta Platforms")
    await map_symbol(db, "FB", meta, date(2012, 5, 18), date(2022, 6, 9))

    assert await db.fetchrow(RESOLVE, "FB", date(2024, 1, 2), NOW) is None


async def test_the_rename_boundary_is_half_open(db: asyncpg.Connection) -> None:
    """On the changeover date the new ticker is live and the old one is not.

    An inclusive upper bound would make both resolve on that day, and a
    resolution that returns two answers is a resolution that picks one silently.
    """
    meta = await new_instrument(db, "META", "Meta Platforms")
    await map_symbol(db, "FB", meta, date(2012, 5, 18), date(2022, 6, 9))
    await map_symbol(db, "META", meta, date(2022, 6, 9), None, datetime(2022, 6, 1, tzinfo=UTC))

    changeover = date(2022, 6, 9)
    assert await db.fetchrow(RESOLVE, "FB", changeover, NOW) is None
    assert await db.fetchrow(RESOLVE, "META", changeover, NOW) is not None


# -------------------------------------------------------- ticker reuse


async def test_a_reused_ticker_resolves_to_different_companies(
    db: asyncpg.Connection,
) -> None:
    """The dangerous one. Keyed by symbol these two would be one price series."""
    old = await new_instrument(db, "XYZ", "Old XYZ Corp", delisted_at=date(2018, 3, 1))
    new = await new_instrument(db, "XYZ", "New XYZ Inc")
    await map_symbol(db, "XYZ", old, date(2005, 1, 1), date(2018, 3, 1))
    await map_symbol(db, "XYZ", new, date(2021, 6, 1), None)

    then = await db.fetchrow(RESOLVE, "XYZ", date(2010, 1, 1), NOW)
    now = await db.fetchrow(RESOLVE, "XYZ", date(2024, 1, 1), NOW)

    assert then["name"] == "Old XYZ Corp"
    assert now["name"] == "New XYZ Inc"
    assert (
        then["instrument_id"] != now["instrument_id"]
    ), "joining these histories creates a handover discontinuity that reads as a gap"


async def test_a_dead_ticker_resolves_to_nothing_between_owners(
    db: asyncpg.Connection,
) -> None:
    """Nobody was quoting XYZ in 2019. The honest answer is no answer."""
    old = await new_instrument(db, "XYZ", "Old XYZ Corp", delisted_at=date(2018, 3, 1))
    new = await new_instrument(db, "XYZ", "New XYZ Inc")
    await map_symbol(db, "XYZ", old, date(2005, 1, 1), date(2018, 3, 1))
    await map_symbol(db, "XYZ", new, date(2021, 6, 1), None)

    assert await db.fetchrow(RESOLVE, "XYZ", date(2019, 1, 1), NOW) is None


# ---------------------------------------------------------- ambiguity


async def test_overlapping_mappings_for_one_ticker_are_refused(
    db: asyncpg.Connection,
) -> None:
    """Refused at write time. Resolving at read time would mean picking silently."""
    a = await new_instrument(db, "XYZ", "A")
    b = await new_instrument(db, "XYZ", "B")
    await map_symbol(db, "XYZ", a, date(2005, 1, 1), date(2018, 3, 1))

    with pytest.raises(asyncpg.PostgresError, match="no_overlapping_symbol"):
        await map_symbol(db, "XYZ", b, date(2010, 1, 1), date(2012, 1, 1))


async def test_an_instrument_cannot_wear_two_tickers_at_once(
    db: asyncpg.Connection,
) -> None:
    """Dual-class shares are separate instruments, so this does not conflict."""
    meta = await new_instrument(db, "META", "Meta Platforms")
    await map_symbol(db, "FB", meta, date(2012, 5, 18), date(2022, 6, 9))

    with pytest.raises(asyncpg.PostgresError, match="no_overlapping_instrument"):
        await map_symbol(db, "FBK", meta, date(2015, 1, 1), date(2016, 1, 1))


async def test_adjacent_ranges_are_allowed(db: asyncpg.Connection) -> None:
    """Half-open ranges abut without overlapping; that is the normal case."""
    old = await new_instrument(db, "XYZ", "Old")
    await map_symbol(db, "XYZ", old, date(2005, 1, 1), date(2018, 3, 1))
    await map_symbol(db, "XYZ", old, date(2018, 3, 1), date(2021, 6, 1))
    assert await db.fetchval("SELECT count(*) FROM symbol_mappings WHERE symbol = 'XYZ'") == 2


async def test_an_inverted_range_is_refused(db: asyncpg.Connection) -> None:
    instrument = await new_instrument(db, "XYZ", "X")
    with pytest.raises(asyncpg.PostgresError, match="range_sane"):
        await map_symbol(db, "XYZ", instrument, date(2020, 1, 1), date(2019, 1, 1))


# ------------------------------------------------------- knowledge time


async def test_a_mapping_we_had_not_learned_of_does_not_resolve(
    db: asyncpg.Connection,
) -> None:
    """R-6.4.a. A rename is announced before it takes effect.

    Meta announced the ticker change on 2022-06-01, effective 2022-06-09. A
    backtest running on 2022-05-01 must not resolve META.
    """
    meta = await new_instrument(db, "META", "Meta Platforms")
    await map_symbol(db, "META", meta, date(2022, 6, 9), None, datetime(2022, 6, 1, tzinfo=UTC))

    unaware = datetime(2022, 5, 1, tzinfo=UTC)
    assert await db.fetchrow(RESOLVE, "META", date(2022, 6, 10), unaware) is None
    assert await db.fetchrow(RESOLVE, "META", date(2022, 6, 10), NOW) is not None


# ------------------------------------------------------------- keying


async def test_bars_are_keyed_by_instrument_not_symbol(db: asyncpg.Connection) -> None:
    key = await db.fetchval(
        "SELECT string_agg(a.attname, ',' ORDER BY k.ord) "
        "FROM pg_index i "
        "JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord) ON true "
        "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum "
        "WHERE i.indrelid = 'bars_daily'::regclass AND i.indisprimary"
    )
    assert key == "instrument_id,session_date"


async def test_a_renamed_company_has_one_contiguous_bar_series(
    db: asyncpg.Connection,
) -> None:
    """The payoff. Bars written under both tickers form one history."""
    meta = await new_instrument(db, "META", "Meta Platforms")
    await map_symbol(db, "FB", meta, date(2012, 5, 18), date(2022, 6, 9))
    await map_symbol(db, "META", meta, date(2022, 6, 9), None, datetime(2022, 6, 1, tzinfo=UTC))

    insert = (
        "INSERT INTO bars_daily (instrument_id, symbol_as_reported, session_date, "
        "open, high, low, close, volume, data_feed) "
        "VALUES ($1, $2, $3, 100, 101, 99, 100, 1000, 'sip')"
    )
    await db.execute(insert, meta, "FB", date(2022, 6, 8))
    await db.execute(insert, meta, "META", date(2022, 6, 9))

    count = await db.fetchval("SELECT count(*) FROM bars_daily WHERE instrument_id = $1", meta)
    assert count == 2, "one query, one company, both sides of the rename"

    tickers = await db.fetchval(
        "SELECT count(DISTINCT symbol_as_reported) FROM bars_daily WHERE instrument_id = $1",
        meta,
    )
    assert tickers == 2, "provenance is preserved: we can still see what the vendor called it"


async def test_universe_snapshots_are_keyed_by_instrument(db: asyncpg.Connection) -> None:
    key = await db.fetchval(
        "SELECT string_agg(a.attname, ',' ORDER BY k.ord) "
        "FROM pg_index i "
        "JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord) ON true "
        "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum "
        "WHERE i.indrelid = 'universe_snapshots'::regclass AND i.indisprimary"
    )
    assert key == "as_of,instrument_id"


async def test_rekeying_populated_bars_is_refused() -> None:
    """The migration guard, on the scenario it actually defends against.

    Bars were ingested against the pre-0005 schema (keyed by symbol), and only
    then is 0005 applied. Rekeying those rows means resolving each one's ticker
    through ``symbol_mappings`` as of its own session date, and verifying the
    result -- a data migration, not a schema change. A silent partial rekey would
    leave half the history unreachable, so the migration refuses and says why.

    Builds the database by hand rather than using the fixture, because the
    fixture applies every migration and the state under test is "stopped at
    0004".
    """
    assert DATABASE_URL is not None
    conn: asyncpg.Connection = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
        for path in MIGRATIONS:
            if path.name.startswith("0005"):
                break
            await conn.execute(path.read_text(encoding="utf-8"))

        await conn.execute("INSERT INTO symbols (symbol, name) VALUES ('META', 'Meta')")
        await conn.execute(
            "INSERT INTO bars_daily (symbol, session_date, open, high, low, close, "
            "volume, data_feed) VALUES ('META', '2026-09-15', 100, 101, 99, 100, 1000, 'sip')"
        )

        migration = next(p for p in MIGRATIONS if p.name.startswith("0005"))
        with pytest.raises(asyncpg.PostgresError, match="verified data migration"):
            await conn.execute(migration.read_text(encoding="utf-8"))
    finally:
        await conn.close()


async def test_rerunning_the_migration_on_populated_migrated_bars_is_a_no_op(
    db: asyncpg.Connection,
) -> None:
    """The complementary case: already migrated, with data, retried.

    A deploy that died after applying 0005 but before recording it must be safe
    to retry. The guard distinguishes "not yet migrated and populated" (refuse)
    from "already migrated" (no-op), and conflating them would make every retry
    on a live database fail.
    """
    meta = await new_instrument(db, "META", "Meta Platforms")
    await db.execute(
        "INSERT INTO bars_daily (instrument_id, symbol_as_reported, session_date, "
        "open, high, low, close, volume, data_feed) "
        "VALUES ($1, 'META', '2026-09-15', 100, 101, 99, 100, 1000, 'sip')",
        meta,
    )
    migration = next(p for p in MIGRATIONS if p.name.startswith("0005"))
    await db.execute(migration.read_text(encoding="utf-8"))

    assert await db.fetchval("SELECT count(*) FROM bars_daily") == 1
