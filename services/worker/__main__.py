"""Worker entrypoint. Ingest and training jobs arrive in Phase 1."""

from __future__ import annotations

from atlas_core.config import bootstrap


def main() -> int:
    config = bootstrap("worker")
    del config
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
