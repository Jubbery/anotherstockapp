"""R-6.4.f — causal windows only.

§9.1 row L7. Pandas makes future leakage a one-character mistake: ``shift(-1)``
instead of ``shift(1)``, ``center=True`` on a rolling window, ``bfill`` on a gap.
Each reaches forward in time, each produces a better backtest, and none produces
an error.

The check is an AST walk rather than a text grep so that a call spread over
several lines, or written with keywords in an unusual order, is still caught, and
so that the patterns appearing in prose and docstrings are not false positives.

Scope is ``libs/atlas_core/features/``, ``libs/atlas_core/labels/`` and the
worker's training code — the places where a time series is transformed. It is
active now, before any of those exist, because the cheapest moment to ban a
one-character mistake is before anyone has had a reason to make it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Directories where time-series transforms live. Missing directories are fine --
# they arrive with their phases.
SCANNED = (
    Path("libs/atlas_core/features"),
    Path("libs/atlas_core/labels"),
    Path("libs/atlas_core/pit"),
    Path("services/worker/training"),
    Path("services/engine/scanner"),
    Path("services/engine/ranking"),
)

# Methods that reach forward in time when called the wrong way.
BACKWARD_FILL_METHODS = frozenset({"bfill", "backfill"})
SHIFT_METHODS = frozenset({"shift", "tshift"})

pytestmark = pytest.mark.leakage


def _scanned_files() -> list[Path]:
    return [
        path
        for directory in SCANNED
        for path in (REPO_ROOT / directory).rglob("*.py")
        if (REPO_ROOT / directory).is_dir()
    ]


def _describe(path: Path, node: ast.AST) -> str:
    return f"{path.relative_to(REPO_ROOT)}:{getattr(node, 'lineno', '?')}"


def _is_negative_number(node: ast.expr) -> bool:
    """True for a literal negative number, including the ``-1`` unary form."""
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return isinstance(node.operand, ast.Constant) and isinstance(
            node.operand.value, int | float
        )
    return isinstance(node, ast.Constant) and isinstance(node.value, int | float) and node.value < 0


def _method_name(call: ast.Call) -> str | None:
    return call.func.attr if isinstance(call.func, ast.Attribute) else None


def test_no_backward_fill() -> None:
    """``bfill`` propagates a future value backwards across a gap."""
    offenders = [
        f"{_describe(path, node)} calls .{_method_name(node)}()"
        for path in _scanned_files()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        if isinstance(node, ast.Call) and _method_name(node) in BACKWARD_FILL_METHODS
    ]
    assert not offenders, (
        "Backward fill found:\n  "
        + "\n  ".join(offenders)
        + "\n\nFilling a gap from the future is lookahead. Forward-fill only (R-6.4.f)."
    )


def test_no_fillna_with_method_bfill() -> None:
    """The same thing, spelled ``fillna(method='bfill')``."""
    offenders = []
    for path in _scanned_files():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
            if not (isinstance(node, ast.Call) and _method_name(node) == "fillna"):
                continue
            for keyword in node.keywords:
                if (
                    keyword.arg == "method"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value in BACKWARD_FILL_METHODS
                ):
                    offenders.append(f"{_describe(path, node)} fillna(method='bfill')")
    assert not offenders, "Backward fill via fillna:\n  " + "\n  ".join(offenders)


def test_no_negative_shift() -> None:
    """``shift(-1)`` pulls tomorrow's value into today's row.

    This is how a label accidentally becomes a feature. It is the single most
    productive way to build a backtest with a Sharpe above 5.
    """
    offenders = []
    for path in _scanned_files():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
            if not (isinstance(node, ast.Call) and _method_name(node) in SHIFT_METHODS):
                continue
            positional = node.args[0] if node.args else None
            keyword = next(
                (kw.value for kw in node.keywords if kw.arg in ("periods", "freq")), None
            )
            if (positional is not None and _is_negative_number(positional)) or (
                keyword is not None and _is_negative_number(keyword)
            ):
                offenders.append(f"{_describe(path, node)} shift with a negative period")
    assert not offenders, (
        "Negative shift found:\n  "
        + "\n  ".join(offenders)
        + "\n\nA negative shift reaches forward in time (R-6.4.f). If a forward-looking "
        "value is genuinely needed, it belongs in labels/, computed by the "
        "triple-barrier code, not in a feature."
    )


def test_no_centered_rolling_windows() -> None:
    """``center=True`` makes a window straddle its own timestamp.

    Half its input is from the future. Pandas defaults to ``center=False``, which
    is why this one survives review: it has to be added deliberately, and it
    still looks harmless.
    """
    offenders = []
    for path in _scanned_files():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if (
                    keyword.arg == "center"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                ):
                    offenders.append(f"{_describe(path, node)} uses center=True")
    assert not offenders, (
        "Centered window found:\n  "
        + "\n  ".join(offenders)
        + "\n\nA centered window includes future bars (R-6.4.f)."
    )


def test_the_scanner_finds_planted_violations() -> None:
    """The guard is only worth having if it fires. Prove it on a synthetic module.

    Written as a self-check because every other test here asserts an *absence*,
    and an absence assertion passes just as happily when the detector is broken.
    """
    source = (
        "def bad(df):\n"
        "    a = df.close.shift(-1)\n"
        "    b = df.close.rolling(20, center=True).mean()\n"
        "    c = df.close.bfill()\n"
        "    d = df.close.fillna(method='bfill')\n"
        "    return a, b, c, d\n"
    )
    tree = ast.parse(source)
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]

    assert any(_method_name(c) in SHIFT_METHODS and _is_negative_number(c.args[0]) for c in calls)
    assert any(
        kw.arg == "center" and isinstance(kw.value, ast.Constant) and kw.value.value is True
        for c in calls
        for kw in c.keywords
    )
    assert any(_method_name(c) in BACKWARD_FILL_METHODS for c in calls)
    assert any(
        kw.arg == "method" and isinstance(kw.value, ast.Constant) and kw.value.value == "bfill"
        for c in calls
        for kw in c.keywords
    )


def test_positive_shift_is_allowed() -> None:
    """``shift(1)`` is the correct, causal lag and must not be flagged."""
    tree = ast.parse("def ok(df):\n    return df.close.shift(1)\n")
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    shift = next(c for c in calls if _method_name(c) in SHIFT_METHODS)
    assert not _is_negative_number(shift.args[0])
