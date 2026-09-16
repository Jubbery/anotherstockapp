"""Ports -- the only place a vendor concept may cross into domain code (§4.3).

Each port is a ``Protocol``. Decision code depends on these; adapters in
``services/*/adapters/`` implement them; ``atlas_core.testing`` provides
deterministic fakes that the backtester is built from (R-4.3.b).

Ports arrive with the phase that needs them, so that none is designed
speculatively:

===================  =====  ====================================================
Port                 Phase  Responsibility
===================  =====  ====================================================
``ClockPort``        0      current time, market session state
``MarketDataPort``   1      historical bars, snapshots, quotes, streams
``ReferenceDataPort``1      asset master, shortability, corporate actions, calendar
``StorePort``        1      domain persistence
``ModelPort``        4      load artifact, predict
``BrokerPort``       5      submit / cancel / replace, account, positions
``NotifierPort``     6      SMS, email
===================  =====  ====================================================
"""

from atlas_core.ports.clock import ClockPort

__all__ = ["ClockPort"]
