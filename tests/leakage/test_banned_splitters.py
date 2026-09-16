"""R-9.4.c: random cross-validation splitters may not appear in training code.

Active from Phase 0 even though ``services/worker/training/`` does not exist yet.
Banning an import before anyone writes it costs nothing; removing it after a
model has been trained costs a retrain and a promotion cycle.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

BANNED = (
    "KFold",
    "StratifiedKFold",
    "train_test_split",
    "cross_val_score",
    "cross_validate",
    "TimeSeriesSplit",  # closer, but still has no purge or embargo
    "ShuffleSplit",
)

SEARCH_ROOTS = ("services", "libs")


def _python_sources() -> list[Path]:
    return [
        path
        for root in SEARCH_ROOTS
        for path in (REPO_ROOT / root).rglob("*.py")
        if "adapters" not in path.parts
    ]


@pytest.mark.leakage
@pytest.mark.parametrize("banned", BANNED)
def test_random_splitters_are_absent(banned: str) -> None:
    """Purged walk-forward with an embargo is the only permitted scheme (§9.4.2)."""
    offenders = [
        path.relative_to(REPO_ROOT)
        for path in _python_sources()
        if banned in path.read_text(encoding="utf-8")
    ]
    assert not offenders, (
        f"{banned} found in {offenders}. Financial labels overlap, so a random split "
        f"puts near-identical samples in train and test (§9.1 L1/L2). Use the purged "
        f"walk-forward splitter in services/worker/training/."
    )
