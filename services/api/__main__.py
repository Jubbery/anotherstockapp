"""Run the API with uvicorn: ``python -m services.api``."""

from __future__ import annotations


def main() -> int:
    import uvicorn

    uvicorn.run("services.api.main:app", host="0.0.0.0", port=8080)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
