"""THE RISK GOVERNOR (§12). Phase 5.

Read MASTER_SPEC §12 in full before adding anything here.

Everything in this package is a pure function: inputs in, decision out. No I/O,
no clock reads, no randomness, no logging, no async (R-12.1.a). That constraint
is what makes 100% branch coverage and property-based testing achievable, and
those are what make R-3.2.b enforceable rather than aspirational.

CI enforces `--cov-branch --cov-fail-under=100` scoped to this package, and a
mutation run must show zero survivors (R-12.6.c).
"""
