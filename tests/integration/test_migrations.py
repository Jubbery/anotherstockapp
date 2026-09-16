"""Migrations apply cleanly, and ``audit_log`` really is append-only.

R-17.4.b requires a migration test that *attempts* an ``UPDATE`` and a ``DELETE``
and asserts they fail. Reading the trigger definition is not the same evidence:
triggers can be created ``DISABLE``d, dropped by a later migration, or bypassed
by a role configuration, and none of that is visible in the DDL that created
them. Phase 8 gate G7 asks for this proof.

Set ``ATLAS_TEST_DATABASE_URL`` to run. CI provides a throwaway Postgres.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = sorted((REPO_ROOT / "db" / "migrations").glob("*.sql"))

DATABASE_URL = os.environ.get("ATLAS_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="ATLAS_TEST_DATABASE_URL is not set; no database to migrate",
)

VALID_ROW = (
    "INSERT INTO audit_log (actor, action, environment, git_sha, config_hash) "
    "VALUES ('engine', 'order.submitted', 'paper', 'deadbeef', 'cfg1')"
)


@pytest.fixture
async def db() -> AsyncIterator[asyncpg.Connection]:
    """A connection to a schema built from the migrations, torn down after."""
    assert DATABASE_URL is not None
    conn: asyncpg.Connection = await asyncpg.connect(DATABASE_URL)
    await conn.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
    for path in MIGRATIONS:
        await conn.execute(path.read_text(encoding="utf-8"))
    try:
        yield conn
    finally:
        await conn.close()


async def test_migrations_apply_in_order(db: asyncpg.Connection) -> None:
    tables = {
        row["tablename"]
        for row in await db.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    }
    assert {"audit_log", "schema_migrations"} <= tables


async def test_migrations_are_idempotent(db: asyncpg.Connection) -> None:
    """Re-running a migration must not fail; a half-applied deploy gets retried."""
    for path in MIGRATIONS:
        await db.execute(path.read_text(encoding="utf-8"))


async def test_audit_row_can_be_inserted(db: asyncpg.Connection) -> None:
    await db.execute(VALID_ROW)
    assert await db.fetchval("SELECT count(*) FROM audit_log") == 1


async def test_audit_log_rejects_update(db: asyncpg.Connection) -> None:
    """R-3.7.b."""
    await db.execute(VALID_ROW)
    with pytest.raises(asyncpg.PostgresError, match="append-only"):
        await db.execute("UPDATE audit_log SET reason = 'tampered'")
    assert await db.fetchval("SELECT count(*) FROM audit_log WHERE reason IS NULL") == 1


async def test_audit_log_rejects_delete(db: asyncpg.Connection) -> None:
    await db.execute(VALID_ROW)
    with pytest.raises(asyncpg.PostgresError, match="append-only"):
        await db.execute("DELETE FROM audit_log")
    assert await db.fetchval("SELECT count(*) FROM audit_log") == 1


async def test_audit_log_rejects_delete_matching_no_rows(db: asyncpg.Connection) -> None:
    """A statement-level trigger fires even when nothing matches.

    A row-level trigger would let ``DELETE FROM audit_log WHERE false`` through,
    which is harmless by itself but means the guard is weaker than it reads.
    """
    with pytest.raises(asyncpg.PostgresError, match="append-only"):
        await db.execute("DELETE FROM audit_log WHERE false")


async def test_audit_log_rejects_truncate(db: asyncpg.Connection) -> None:
    """TRUNCATE is not a DELETE and needs its own trigger."""
    with pytest.raises(asyncpg.PostgresError, match="append-only"):
        await db.execute("TRUNCATE audit_log")


async def test_the_table_owner_cannot_bypass_the_trigger(db: asyncpg.Connection) -> None:
    """R-3.7.b says 'all roles including the table owner'.

    Anyone holding the service role key is the owner here, so a guard that the
    owner can step around would not be a guard at all.
    """
    is_superuser = await db.fetchval("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
    assert is_superuser, "this test is only meaningful as a privileged role"
    await db.execute(VALID_ROW)
    with pytest.raises(asyncpg.PostgresError, match="append-only"):
        await db.execute("DELETE FROM audit_log")


async def test_environment_must_be_paper_or_live(db: asyncpg.Connection) -> None:
    """R-11.1.d: an audit row that cannot tell paper from live is not an audit row."""
    with pytest.raises(asyncpg.PostgresError, match="audit_log_environment_known"):
        await db.execute(
            "INSERT INTO audit_log (actor, action, environment, git_sha, config_hash) "
            "VALUES ('engine', 'x', 'prod', 'a', 'b')"
        )


async def test_row_level_security_is_enabled_on_every_table(db: asyncpg.Connection) -> None:
    """R-16.4.a. Checked per-table so a new migration cannot forget it."""
    unprotected = [
        row["relname"]
        for row in await db.fetch(
            "SELECT c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r' "
            "AND (NOT c.relrowsecurity OR NOT c.relforcerowsecurity)"
        )
    ]
    assert not unprotected, f"RLS not enabled and forced on: {unprotected} (R-16.4.a)"
