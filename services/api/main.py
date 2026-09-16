"""API entrypoint.

The control plane proper is Phase 6. What exists now is the environment guard and
a liveness probe that deliberately exposes no internal state (§14.2).
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from atlas_core.config import bootstrap
from atlas_core.domain.time import utc_now

CONFIG = bootstrap("api")

app = FastAPI(
    title="Atlas control plane",
    version="0.0.0",
    docs_url=None,  # Phase 6: behind auth. Nothing about this account is public.
    redoc_url=None,
)


@app.get("/v1/health")
def health() -> dict[str, Any]:
    """Liveness only. No account state, no positions, no config detail."""
    return {
        "status": "ok",
        "environment": CONFIG.label,
        "server_time": utc_now().isoformat(),
    }
