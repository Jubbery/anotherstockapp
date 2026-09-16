# Sources

Every external fact this project depends on, where it came from, and when it was checked.
Facts decay — a rate, an entitlement, or a regulation confirmed a year ago is not confirmed (R-19.1.d).

**Rule:** if a number appears in the specification, in config, or in code, it has a row here.

| # | Fact | Value | Source | Checked | Checked by | Next review |
|---|---|---|---|---|---|---|
| S-1 | Alpaca SIP data feed pricing and entitlement | **UNVERIFIED** — assumed ~$99/mo "Algo Trader Plus" | — | — | — | blocks O-1 / Phase 1 |
| S-2 | SEC Section 31 fee rate (sell side) | **UNVERIFIED** | — | — | — | blocks Phase 3 |
| S-3 | FINRA TAF per-share rate and cap (sell side) | **UNVERIFIED** | — | — | — | blocks Phase 3 |
| S-4 | Alpaca API rate limits (REST, per key) | **UNVERIFIED** | — | — | — | blocks Phase 1 |
| S-5 | PDT rule status — operator states retired June 2026 | **UNVERIFIED by Atlas** | operator statement, 2026-09-16 | — | — | blocks O-4 / Phase 8 (R-2.4.b) |
| S-6 | Alpaca equity commission | assumed $0.00 | — | — | — | blocks Phase 3 |
| S-7 | Exchange calendar incl. 2026 half-days | to come from `ReferenceDataPort` | — | — | — | Phase 1 |
| S-8 | Alpaca paper/live base URLs | — | — | — | — | Phase 0 |

## How to add a row

Check the fact against a primary source — the vendor's own documentation, the regulator's own notice,
or an API response you captured. Record the value, the URL or API endpoint, today's date, and who
checked it. If you learned it through the Alpaca MCP, also write the observation up in
`docs/research/` (R-19.1.c) and link it here.

A fact marked **UNVERIFIED** may not be relied on by code that runs with real money.
