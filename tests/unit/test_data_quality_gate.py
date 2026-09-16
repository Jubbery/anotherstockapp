"""§6.7 — the data quality gate.

R-6.7.a: a BLOCK stops the engine leaving WARMUP, and there is no override. The
tests that matter most here are the ones asserting a *failure* blocks, and the
one asserting an empty gate blocks rather than passes.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from atlas_core.quality import DataQualityInputs, GateResult, Severity, run_gate
from atlas_core.quality.gate import CHECKS


def healthy(**overrides: object) -> DataQualityInputs:
    """A clean nightly run. Every test perturbs exactly one thing from here."""
    base: dict[str, object] = {
        "as_of": date(2026, 9, 16),
        "universe_size": 8_143,
        "symbols_with_daily_bars": 8_140,
        "top_liquid_size": 1_500,
        "expected_minute_bars": 585_000,
        "actual_minute_bars": 583_000,
        "duplicate_bar_keys": 0,
        "bar_invariant_violations": 0,
        "unaligned_minute_bars": 0,
        "calendar_has_today": True,
        "calendar_forward_sessions": 62,
        "broker_close_sample_size": 20,
        "broker_close_mismatches": 0,
        "median_abs_daily_return": Decimal("0.012"),
        "extreme_move_count": 3,
        "extreme_move_trailing_mean": Decimal("4"),
        "corporate_actions_ingested": 17,
        "prior_session_was_trading_day": True,
        "ingest_reject_rate": Decimal("0.0001"),
        "partition_years_remaining": 4,
    }
    base.update(overrides)
    return DataQualityInputs(**base)  # type: ignore[arg-type]


def test_a_clean_night_passes() -> None:
    result = run_gate(healthy())
    assert result.overall is Severity.PASS
    assert not result.blocks_trading
    assert result.failures() == ()
    assert "all 12 checks passed" in result.summary()


# ---------------------------------------------------------------- BLOCK cases


@pytest.mark.parametrize(
    ("overrides", "expected_check"),
    [
        ({"symbols_with_daily_bars": 7_000}, "daily_bar_coverage"),
        ({"actual_minute_bars": 500_000}, "minute_bar_coverage"),
        ({"duplicate_bar_keys": 1}, "no_duplicate_bars"),
        ({"bar_invariant_violations": 1}, "bar_invariants"),
        ({"unaligned_minute_bars": 1}, "minute_bar_alignment"),
        ({"calendar_has_today": False}, "calendar_coverage"),
        ({"calendar_forward_sessions": 5}, "calendar_coverage"),
        ({"broker_close_mismatches": 1}, "broker_close_agreement"),
    ],
)
def test_these_failures_stop_the_engine(overrides: dict[str, object], expected_check: str) -> None:
    """Each of these means we cannot vouch for the day's data."""
    result = run_gate(healthy(**overrides))
    assert result.blocks_trading, f"{expected_check} should have blocked"
    assert expected_check in {check.name for check in result.failures()}


def test_one_duplicate_bar_is_enough_to_block() -> None:
    """Not a percentage. One double-counted bar distorts every average over it."""
    assert run_gate(healthy(duplicate_bar_keys=1)).blocks_trading


def test_a_too_small_broker_sample_blocks() -> None:
    """Zero mismatches out of two symbols is not evidence of agreement."""
    result = run_gate(healthy(broker_close_sample_size=2, broker_close_mismatches=0))
    assert result.blocks_trading


# ----------------------------------------------------------------- WARN cases


@pytest.mark.parametrize(
    ("overrides", "expected_check"),
    [
        ({"median_abs_daily_return": Decimal("0.30")}, "median_daily_return_sane"),
        ({"median_abs_daily_return": Decimal("0.0001")}, "median_daily_return_sane"),
        ({"extreme_move_count": 40}, "extreme_move_count"),
        ({"corporate_actions_ingested": 0}, "corporate_actions_ingested"),
        ({"ingest_reject_rate": Decimal("0.02")}, "ingest_reject_rate"),
        ({"partition_years_remaining": 1}, "partition_headroom"),
    ],
)
def test_these_warn_but_do_not_stop_trading(
    overrides: dict[str, object], expected_check: str
) -> None:
    result = run_gate(healthy(**overrides))
    assert result.overall is Severity.WARN
    assert not result.blocks_trading
    assert expected_check in {check.name for check in result.failures()}


def test_a_block_outranks_a_warn() -> None:
    result = run_gate(healthy(duplicate_bar_keys=1, ingest_reject_rate=Decimal("0.02")))
    assert result.overall is Severity.BLOCK
    assert len(result.failures()) == 2


def test_no_corporate_actions_after_a_holiday_is_not_a_finding() -> None:
    result = run_gate(healthy(corporate_actions_ingested=0, prior_session_was_trading_day=False))
    assert result.overall is Severity.PASS


def test_extreme_move_check_waits_for_a_baseline() -> None:
    """Early in the history there is nothing to compare against."""
    result = run_gate(healthy(extreme_move_count=999, extreme_move_trailing_mean=None))
    assert result.overall is Severity.PASS


# ------------------------------------------------------------ vacuous passes


def test_an_empty_universe_blocks_rather_than_passing() -> None:
    """Zero over zero is not full coverage.

    A collector that returns nothing has told us nothing, and treating silence
    as approval is how a broken metrics job becomes a green light to trade.
    """
    result = run_gate(healthy(universe_size=0, symbols_with_daily_bars=0))
    assert result.blocks_trading


def test_zero_expected_minute_bars_blocks() -> None:
    result = run_gate(healthy(expected_minute_bars=0, actual_minute_bars=0))
    assert result.blocks_trading


def test_a_gate_that_ran_no_checks_blocks() -> None:
    """The degenerate case, stated explicitly because it is the dangerous one."""
    assert GateResult(as_of=date(2026, 9, 16), results=()).blocks_trading


# ------------------------------------------------------------------ structure


def test_every_check_runs_even_after_a_block() -> None:
    """The operator needs the whole picture to fix the day in one pass."""
    result = run_gate(healthy(duplicate_bar_keys=1))
    assert len(result.results) == len(CHECKS)


def test_check_names_are_unique() -> None:
    result = run_gate(healthy())
    names = [check.name for check in result.results]
    assert len(names) == len(set(names))


def test_every_check_explains_itself() -> None:
    """A failure the operator cannot act on is an alert they learn to ignore."""
    for check in run_gate(healthy()).results:
        assert len(check.detail) > 40, f"{check.name} needs a real explanation"
        assert check.threshold


def test_there_is_no_override() -> None:
    """R-6.7.a. Asserted against the source, so adding one fails the build.

    Docstrings are stripped first: the module states the rule in prose, and a raw
    text search would match its own explanation. Same treatment as
    ``test_no_hardcoded_session_times_in_the_time_module``.
    """
    import ast
    import inspect

    from atlas_core.quality import gate

    tree = ast.parse(inspect.getsource(gate))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node.value = ""
    code = ast.unparse(tree).lower()

    for forbidden in ("override", "force_pass", "skip_gate", "ignore_block", "bypass"):
        assert forbidden not in code, (
            f"{forbidden!r} appears in the gate's code. R-6.7.a: fixing the data is the "
            f"only path forward -- there is no override."
        )
