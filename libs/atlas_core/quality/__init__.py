"""The data quality gate (MASTER_SPEC §6.7)."""

from atlas_core.quality.gate import (
    CheckResult,
    DataQualityInputs,
    GateResult,
    Severity,
    run_gate,
)

__all__ = ["CheckResult", "DataQualityInputs", "GateResult", "Severity", "run_gate"]
