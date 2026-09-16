"""Migration hygiene that needs no database.

Kept out of ``tests/integration/`` deliberately: the forward-only guarantee
(R-C.a) should be checked on every machine and in every CI job, not only where a
Postgres happens to be available. A guard that skips silently is not a guard.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = sorted((REPO_ROOT / "db" / "migrations").glob("*.sql"))


def test_there_is_at_least_one_migration() -> None:
    assert MIGRATIONS, "no migrations found; the checksum guard would pass vacuously"


def test_released_migrations_are_not_edited() -> None:
    """R-C.a: forward-only. A correction is a new file, never an edit.

    The checksums in ``CHECKSUMS.txt`` are recorded when a migration is first
    released. A mismatch means a migration that has already run somewhere was
    changed, so that database and this repository no longer describe the same
    schema -- and nothing else in the pipeline would notice.
    """
    actual = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()[:16] for path in MIGRATIONS}

    expected: dict[str, str] = {}
    for line in (REPO_ROOT / "db" / "migrations" / "CHECKSUMS.txt").read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        name, digest = line.split("  ", 1)
        expected[name] = digest.strip()

    # Every migration is recorded. A new file with no entry is a migration that
    # slipped past the ledger, which is the same blind spot as an edited one.
    assert set(actual) == set(expected), (
        f"CHECKSUMS.txt does not cover the migrations on disk. "
        f"Missing: {sorted(set(actual) - set(expected))}, "
        f"stale: {sorted(set(expected) - set(actual))}."
    )

    changed = [name for name, digest in actual.items() if expected[name] != digest]
    assert not changed, (
        f"Released migrations were edited: {changed}. Migrations are forward-only "
        f"-- add a new migration instead (R-C.a)."
    )
