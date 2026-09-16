"""The data quality gate.

R-6.7.a: a **BLOCK** result prevents the engine leaving ``WARMUP`` and notifies
the operator. **There is no override flag.** Fixing the data is the only path
forward, and that is not an inconvenience to be engineered around — Atlas does
not trade on data it cannot vouch for, and the cheapest place to discover bad
data is before the engine is built on top of it.

The checks are **pure functions** of a metrics snapshot, for the same reason the
risk governor is (R-12.1.a): a gate that reaches out to a database mid-evaluation
is a gate whose verdict depends on when you asked. Gathering the metrics is the
adapter's job; deciding is this module's.

Severity is deliberately coarse. A check either stops trading or it does not;
a middle category that "sort of" stops trading is one that gets ignored.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

__all__ = [
    "CheckResult",
    "DataQualityInputs",
    "GateResult",
    "Severity",
    "run_gate",
]


class Severity(StrEnum):
    """Ordered worst-last so ``max`` gives the overall verdict."""

    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


_RANK = {Severity.PASS: 0, Severity.WARN: 1, Severity.BLOCK: 2}


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    severity: Severity
    passed: bool
    detail: str
    value: str | None = None
    threshold: str | None = None

    @property
    def effective_severity(self) -> Severity:
        """A passing check contributes nothing, whatever its configured severity."""
        return Severity.PASS if self.passed else self.severity


@dataclass(frozen=True, slots=True)
class GateResult:
    as_of: date
    results: tuple[CheckResult, ...]

    @property
    def overall(self) -> Severity:
        if not self.results:
            # An empty gate is not a passing gate. A run that checked nothing has
            # told us nothing, and treating silence as approval is how a broken
            # metrics collector becomes a green light.
            return Severity.BLOCK
        return max(
            (result.effective_severity for result in self.results),
            key=lambda severity: _RANK[severity],
        )

    @property
    def blocks_trading(self) -> bool:
        """R-6.7.a. The engine reads this before leaving WARMUP."""
        return self.overall is Severity.BLOCK

    def failures(self) -> tuple[CheckResult, ...]:
        return tuple(result for result in self.results if not result.passed)

    def summary(self) -> str:
        failed = self.failures()
        if not failed:
            return f"{self.as_of}: all {len(self.results)} checks passed"
        names = ", ".join(f"{r.name}({r.effective_severity.value})" for r in failed)
        return f"{self.as_of}: {len(failed)}/{len(self.results)} checks failed -- {names}"


@dataclass(frozen=True, slots=True)
class DataQualityInputs:
    """Metrics gathered by the adapter. Every field is an observation, not a verdict.

    Defaults are deliberately absent for the BLOCK-severity inputs: an adapter
    that fails to collect one should raise a ``TypeError`` at construction rather
    than silently supply a passing value.
    """

    as_of: date

    # Coverage
    universe_size: int
    symbols_with_daily_bars: int
    top_liquid_size: int
    expected_minute_bars: int
    actual_minute_bars: int

    # Integrity
    duplicate_bar_keys: int
    bar_invariant_violations: int
    unaligned_minute_bars: int

    # Calendar
    calendar_has_today: bool
    calendar_forward_sessions: int

    # Broker cross-check
    broker_close_sample_size: int
    broker_close_mismatches: int

    # Distribution (WARN territory)
    median_abs_daily_return: Decimal | None = None
    extreme_move_count: int = 0
    extreme_move_trailing_mean: Decimal | None = None
    corporate_actions_ingested: int = 0
    prior_session_was_trading_day: bool = True
    ingest_reject_rate: Decimal = Decimal(0)

    # Partition headroom (see 0004_bars_daily_partitions.sql)
    partition_years_remaining: int = 99


@dataclass(frozen=True, slots=True)
class Thresholds:
    """§6.7's table, as configuration. Every value is a starting point."""

    min_daily_coverage: Decimal = Decimal("0.995")
    min_minute_coverage: Decimal = Decimal("0.99")
    min_forward_sessions: int = 30
    median_return_low: Decimal = Decimal("0.002")
    median_return_high: Decimal = Decimal("0.05")
    extreme_move_multiple: Decimal = Decimal(2)
    max_reject_rate: Decimal = Decimal("0.005")
    min_partition_years: int = 2
    min_broker_sample: int = 20


def _ratio(numerator: int, denominator: int) -> Decimal:
    """Zero over zero is not one.

    A universe of zero symbols with zero bars is 100% covered only in the sense
    that nothing is missing because nothing exists. That is a collector failure,
    and it must fail the gate rather than pass it vacuously.
    """
    if denominator <= 0:
        return Decimal(0)
    return Decimal(numerator) / Decimal(denominator)


# Each check is (name, severity, predicate). Kept as a table so the set of checks
# is readable in one screen and so adding one cannot forget to declare severity.
Check = Callable[[DataQualityInputs, Thresholds], CheckResult]


def _check_daily_coverage(i: DataQualityInputs, t: Thresholds) -> CheckResult:
    coverage = _ratio(i.symbols_with_daily_bars, i.universe_size)
    return CheckResult(
        name="daily_bar_coverage",
        severity=Severity.BLOCK,
        passed=i.universe_size > 0 and coverage >= t.min_daily_coverage,
        value=f"{coverage:.4f}",
        threshold=f">={t.min_daily_coverage}",
        detail=(
            f"{i.symbols_with_daily_bars}/{i.universe_size} snapshot symbols have a "
            f"daily bar. Missing bars mean Stage A ranks an incomplete universe."
        ),
    )


def _check_minute_coverage(i: DataQualityInputs, t: Thresholds) -> CheckResult:
    coverage = _ratio(i.actual_minute_bars, i.expected_minute_bars)
    return CheckResult(
        name="minute_bar_coverage",
        severity=Severity.BLOCK,
        passed=i.expected_minute_bars > 0 and coverage >= t.min_minute_coverage,
        value=f"{coverage:.4f}",
        threshold=f">={t.min_minute_coverage}",
        detail=(
            f"{i.actual_minute_bars}/{i.expected_minute_bars} expected minute bars for the "
            f"top {i.top_liquid_size} names. A window containing a silently missing bar "
            f"produces a wrong feature (R-6.5.b)."
        ),
    )


def _check_no_duplicates(i: DataQualityInputs, t: Thresholds) -> CheckResult:
    return CheckResult(
        name="no_duplicate_bars",
        severity=Severity.BLOCK,
        passed=i.duplicate_bar_keys == 0,
        value=str(i.duplicate_bar_keys),
        threshold="==0",
        detail="Duplicate (symbol, ts) keys double-count volume and distort every average.",
    )


def _check_bar_invariants(i: DataQualityInputs, t: Thresholds) -> CheckResult:
    return CheckResult(
        name="bar_invariants",
        severity=Severity.BLOCK,
        passed=i.bar_invariant_violations == 0,
        value=str(i.bar_invariant_violations),
        threshold="==0",
        detail="R-6.6.b: low<=open,close<=high, volume>=0. A violation is a parsing bug.",
    )


def _check_bar_alignment(i: DataQualityInputs, t: Thresholds) -> CheckResult:
    return CheckResult(
        name="minute_bar_alignment",
        severity=Severity.BLOCK,
        passed=i.unaligned_minute_bars == 0,
        value=str(i.unaligned_minute_bars),
        threshold="==0",
        detail=(
            "R-6.4.g: bars must sit on the minute grid. An unaligned timestamp means the "
            "vendor's convention is not the one every feature window assumes."
        ),
    )


def _check_calendar(i: DataQualityInputs, t: Thresholds) -> CheckResult:
    ok = i.calendar_has_today and i.calendar_forward_sessions >= t.min_forward_sessions
    return CheckResult(
        name="calendar_coverage",
        severity=Severity.BLOCK,
        passed=ok,
        value=f"today={i.calendar_has_today}, forward={i.calendar_forward_sessions}",
        threshold=f">={t.min_forward_sessions} forward sessions",
        detail=(
            "R-5.4.c: session boundaries come from the calendar. Without it the engine "
            "cannot know when to stop entering or when to force-flatten."
        ),
    )


def _check_broker_close_agreement(i: DataQualityInputs, t: Thresholds) -> CheckResult:
    enough = i.broker_close_sample_size >= t.min_broker_sample
    return CheckResult(
        name="broker_close_agreement",
        severity=Severity.BLOCK,
        passed=enough and i.broker_close_mismatches == 0,
        value=f"{i.broker_close_mismatches} mismatches in {i.broker_close_sample_size}",
        threshold=f"0 mismatches, sample >={t.min_broker_sample}",
        detail=(
            "Our stored close must match the broker's within a tick. A disagreement means "
            "we and the venue we trade on do not share a view of yesterday."
        ),
    )


def _check_median_return(i: DataQualityInputs, t: Thresholds) -> CheckResult:
    value = i.median_abs_daily_return
    ok = value is not None and t.median_return_low <= value <= t.median_return_high
    return CheckResult(
        name="median_daily_return_sane",
        severity=Severity.WARN,
        passed=ok,
        value=str(value),
        threshold=f"[{t.median_return_low}, {t.median_return_high}]",
        detail=(
            "A market-wide median outside this band usually means an adjustment bug "
            "rather than an unusual day -- a mishandled split shows up here first."
        ),
    )


def _check_extreme_moves(i: DataQualityInputs, t: Thresholds) -> CheckResult:
    trailing = i.extreme_move_trailing_mean
    if trailing is None or trailing <= 0:
        # No baseline yet (early in the history). Not a finding.
        return CheckResult(
            name="extreme_move_count",
            severity=Severity.WARN,
            passed=True,
            value=str(i.extreme_move_count),
            threshold="no baseline yet",
            detail="Insufficient trailing history to judge; check re-arms once 30 days exist.",
        )
    limit = trailing * t.extreme_move_multiple
    return CheckResult(
        name="extreme_move_count",
        severity=Severity.WARN,
        passed=Decimal(i.extreme_move_count) <= limit,
        value=str(i.extreme_move_count),
        threshold=f"<={limit}",
        detail=(
            "A spike in >50% single-day moves is more often unhandled splits than a "
            "market event."
        ),
    )


def _check_corporate_actions(i: DataQualityInputs, t: Thresholds) -> CheckResult:
    expected = i.prior_session_was_trading_day
    return CheckResult(
        name="corporate_actions_ingested",
        severity=Severity.WARN,
        passed=(not expected) or i.corporate_actions_ingested > 0,
        value=str(i.corporate_actions_ingested),
        threshold=">0 after a trading day",
        detail=(
            "Zero actions after a full session is possible but unusual; it is more often "
            "a silently failing feed, and a missed split corrupts the adjusted series."
        ),
    )


def _check_reject_rate(i: DataQualityInputs, t: Thresholds) -> CheckResult:
    return CheckResult(
        name="ingest_reject_rate",
        severity=Severity.WARN,
        passed=i.ingest_reject_rate <= t.max_reject_rate,
        value=str(i.ingest_reject_rate),
        threshold=f"<={t.max_reject_rate}",
        detail="R-6.6.a: a rising reject rate is a leading indicator of a vendor change.",
    )


def _check_partition_headroom(i: DataQualityInputs, t: Thresholds) -> CheckResult:
    return CheckResult(
        name="partition_headroom",
        severity=Severity.WARN,
        passed=i.partition_years_remaining >= t.min_partition_years,
        value=str(i.partition_years_remaining),
        threshold=f">={t.min_partition_years} years",
        detail=(
            "bars_daily has no default partition, so an insert past the last declared "
            "year fails outright. Warn well before that happens."
        ),
    )


CHECKS: Sequence[Check] = (
    _check_daily_coverage,
    _check_minute_coverage,
    _check_no_duplicates,
    _check_bar_invariants,
    _check_bar_alignment,
    _check_calendar,
    _check_broker_close_agreement,
    _check_median_return,
    _check_extreme_moves,
    _check_corporate_actions,
    _check_reject_rate,
    _check_partition_headroom,
)

DEFAULT_THRESHOLDS = Thresholds()


def run_gate(
    inputs: DataQualityInputs,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
    checks: Sequence[Check] = CHECKS,
) -> GateResult:
    """Evaluate every check. Never short-circuits.

    Running all of them even after the first BLOCK is deliberate: the operator
    needs the whole picture to fix the day's data, and stopping at the first
    failure turns one debugging session into several.
    """
    return GateResult(
        as_of=inputs.as_of,
        results=tuple(check(inputs, thresholds) for check in checks),
    )
