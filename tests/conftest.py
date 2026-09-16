"""Global test guards.

R-18.2.b: no test may place an order against a live account. The guard is a
session fixture rather than a convention because the cost of the convention
failing once is unbounded.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _never_live() -> None:
    """Abort the whole session if it was started against the live environment."""
    if os.environ.get("ALPACA_ENV") == "live":
        pytest.exit(
            "Refusing to run the test suite with ALPACA_ENV=live (R-18.2.b).",
            returncode=2,
        )


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove Atlas environment variables so no test inherits an ambient value.

    A test that passes because the developer happened to have ALPACA_ENV exported
    is a test that proves nothing.
    """
    for name in (
        "ALPACA_ENV",
        "ATLAS_PHASE",
        "ATLAS_LIVE_CONFIRMED",
        "ALPACA_PAPER_API_KEY_ID",
        "ALPACA_PAPER_API_SECRET_KEY",
        "ALPACA_LIVE_API_KEY_ID",
        "ALPACA_LIVE_API_SECRET_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
