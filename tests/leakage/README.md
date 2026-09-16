# Leakage suite

Implements the `Test` column of MASTER_SPEC §9.1. **A failure here blocks merge**
(R-9.1.a).

These tests protect against a class of bug that produces *better* results when
broken — a lookahead makes the backtest's Sharpe go up, not down — which means
no other signal in the project will catch it. That is why the suite exists
separately from `tests/unit/` and why it is not skippable.

| Test | Guards | Phase |
|---|---|---|
| `test_no_future_ops` | R-6.4.f — no centered windows, `shift(-n)`, `bfill` | 1 |
| `test_knowledge_time_filter` | R-6.4.a — restatable tables queried with `as_of` | 1 |
| `test_universe_is_as_of` | R-6.4.b — no survivorship bias | 1 |
| `test_adjustment_is_as_of` | R-6.4.d — splits do not rewrite history | 1 |
| `test_bar_alignment` | R-6.4.g — bar-open convention, no same-bar decisions | 1 |
| `test_no_global_fit` | L3 — transforms fit inside the fold | 4 |
| `test_cv_is_time_ordered` | R-9.4.b — purged walk-forward only | 4 |
| `test_purge_removes_overlap` | L2 — label windows do not straddle the split | 4 |
| `test_labels_include_costs` | R-9.3.b | 4 |
| `test_labels_respect_stage_a` | R-4.4.b | 4 |
| `test_sample_weights` | R-9.4.d | 4 |
| `test_trials_counted` | R-8.5.b | 4 |
| `test_feature_parity` | **R-9.2.e** — the one that matters most | 4 |
| `test_halted_not_fillable` | L14 | 3 |

`test_banned_splitters` (R-9.4.c) is active now, because the cheapest time to
ban an import is before anyone has written the line.
