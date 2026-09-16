"""R-10.1.c: exactly one module may call the broker's order API.

Active from Phase 0. The check is an AST walk rather than a grep so that a call
spread over several lines, or reached through an alias, is still caught.

Like the splitter ban, this exists before the code it governs. The moment a
second order path is convenient is the moment it gets written, and this test is
what makes that a failing build rather than a code-review judgement call.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Method names on BrokerPort that place, change, or withdraw an order.
ORDER_METHODS = frozenset(
    {
        "submit_order",
        "cancel_order",
        "replace_order",
        "cancel_all_orders",
        "close_position",
        "close_all_positions",
    }
)

# The single path (R-10.1.a/d), plus the adapters that implement the port and the
# deterministic fakes the backtester is built from (R-4.3.b).
PERMITTED = (
    Path("services/engine/execution/submit.py"),
    Path("services/engine/execution/cancel.py"),
    Path("libs/atlas_core/ports/broker.py"),
)
PERMITTED_DIRS = (
    Path("services/engine/adapters"),
    Path("libs/atlas_core/testing"),
)


def _is_permitted(relative: Path) -> bool:
    return relative in PERMITTED or any(
        directory in relative.parents for directory in PERMITTED_DIRS
    )


def _call_sites(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name in ORDER_METHODS:
                found.append((node.lineno, name))
    return found


def test_only_the_single_path_calls_the_broker() -> None:
    offenders: list[str] = []
    for root in ("services", "libs"):
        for path in (REPO_ROOT / root).rglob("*.py"):
            relative = path.relative_to(REPO_ROOT)
            if _is_permitted(relative):
                continue
            offenders += [f"{relative}:{line} calls {name}()" for line, name in _call_sites(path)]

    assert not offenders, (
        "Broker order calls found outside the single submission path (R-10.1.a):\n  "
        + "\n  ".join(offenders)
        + "\n\nEvery order reaches the broker through submit_order_through_governor, "
        "which runs the risk governor first. There is no bypass parameter."
    )


@pytest.mark.parametrize("forbidden", ["force=True", "bypass_risk", "skip_risk", "dry_run=False"])
def test_no_risk_bypass_parameters_exist(forbidden: str) -> None:
    """R-10.1.c: no parameter, flag, or helper may skip the governor."""
    offenders = [
        path.relative_to(REPO_ROOT)
        for root in ("services", "libs")
        for path in (REPO_ROOT / root).rglob("*.py")
        if forbidden in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"{forbidden!r} found in {offenders} -- see R-10.1.c"
