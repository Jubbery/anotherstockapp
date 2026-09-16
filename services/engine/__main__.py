"""Engine entrypoint.

Phase 5 builds the state machine in §4.6. Today this exists so that R-11.1.a is
enforced and tested from the first commit: the environment guard is the one piece
of the engine that must never have been absent.
"""

from __future__ import annotations

from atlas_core.config import bootstrap


def main() -> int:
    config = bootstrap("engine")
    # Phase 5: acquire the singleton lease (R-4.2.a), verify the model artifact
    # against the feature set version (R-9.8.b), then enter BOOT -> WARMUP (§4.6).
    del config
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
