"""Point-in-time correctness.

Everything here answers one question: *what did the world look like at time T,
using only what was knowable at time T?* Getting this wrong does not produce an
error — it produces a better backtest, which is why the machinery is isolated in
its own package with its own tests rather than spread through the ingest code.

MASTER_SPEC §6.4, and the leakage table rows L4, L5, L12 in §9.1.
"""

from atlas_core.pit.adjustment import (
    AdjustmentFactors,
    adjust_bar,
    adjustment_factors,
    knowable_actions,
)
from atlas_core.pit.universe import (
    SurvivorshipError,
    UniverseEntry,
    UniverseSnapshot,
    assert_retains_delistings,
)

__all__ = [
    "AdjustmentFactors",
    "adjust_bar",
    "adjustment_factors",
    "knowable_actions",
    "SurvivorshipError",
    "UniverseEntry",
    "UniverseSnapshot",
    "assert_retains_delistings",
]
