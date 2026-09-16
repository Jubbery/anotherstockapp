"""Deterministic fakes for every port (R-4.3.b).

These are not test helpers in the usual sense -- the backtester is built from
them (R-8.2.a), so a fake that diverges from the real adapter's behaviour is a
backtest that diverges from production. Fakes enforce the same constraints the
real service does (R-8.2.b).
"""

from atlas_core.testing.clock import FrozenClock

__all__ = ["FrozenClock"]
