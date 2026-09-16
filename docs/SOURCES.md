# Sources

Every external fact this project depends on, where it came from, and when it was
checked. Facts decay — a rate or entitlement confirmed a year ago is not
confirmed (R-19.1.d).

**Rule:** if a number appears in the specification, in config, or in code, it has
a row here.

## Status vocabulary

| Status | Meaning | May code that trades real money rely on it? |
|---|---|---|
| **VERIFIED** | Read from the primary source (the vendor's or regulator's own page, or a captured API response) on the date shown | Yes |
| **PROVISIONAL** | Found via web search summaries only; the primary source was unreachable | **No.** Usable for design and backtest scaffolding, not for live |
| **UNVERIFIED** | Assumed, or asserted without a source | **No** |

## Facts

| # | Fact | Value | Status | Source | Checked | Blocks |
|---|---|---|---|---|---|---|
| S-1 | Alpaca SIP feed plan and price | "Algo Trader Plus", **$99/month**, full SIP real-time (CTA + UTP), OPRA options | PROVISIONAL | Web search summaries of `docs.alpaca.markets/us/docs/about-market-data-api` and `alpaca.markets/data` | 2026-09-16 | **O-1 / Phase 1** |
| S-2 | Alpaca API rate limit on that plan | **10,000 requests/minute** | PROVISIONAL | Same as S-1 | 2026-09-16 | Phase 1 (R-6.2.c) |
| S-3 | SEC Section 31 fee (sell side) | **$20.60 per $1,000,000** of covered sales, effective **2026-04-04**. Rate was **$0.00/million** for charge dates through 2026-04-03 | PROVISIONAL | SEC Fee Rate Advisory FY2026 (`sec.gov/rules-regulations/fee-rate-advisories/2026-2`); FINRA Information Notice 2026-03-17; Federal Register 2026-04233 | 2026-09-16 | Phase 3 |
| S-4 | FINRA Trading Activity Fee (sell side, covered equity) | **$0.000195 per share**, cap **$9.79 per trade**, effective **2026-01-01** (raised from $0.000166) | PROVISIONAL | FINRA "Trading Activity Fee" guidance page | 2026-09-16 | Phase 3 |
| S-5 | Alpaca equity commission | Assumed **$0.00** | UNVERIFIED | — | — | Phase 3 |
| S-6 | PDT rule status | Operator states the rule was retired in June 2026 | **UNVERIFIED by Atlas** | Operator statement, 2026-09-16 | — | **O-4 / Phase 8** (R-2.4.b) |
| S-7 | Alpaca paper / live base URLs | `https://paper-api.alpaca.markets` / `https://api.alpaca.markets` | PROVISIONAL | Alpaca SDK convention; encoded in `libs/atlas_core/config/env.py` | 2026-09-16 | Phase 5 |
| S-8 | Exchange calendar incl. 2026 half-days | To come from `ReferenceDataPort` at ingest, not from a static table | UNVERIFIED | — | — | Phase 1 (R-5.4.c) |
| S-9 | Alpaca borrow rates for shorts | Per-symbol, varies; default placeholder 300 bps annual | UNVERIFIED | — | — | Phase 3 (R-8.3.a) |

## Why S-3 matters more than it looks

The Section 31 rate went from **$0.00/million to $20.60/million on 2026-04-04**.
A backtest spanning that date and applying today's rate to the whole period
overstates costs before April and understates nothing after — the opposite
error is worse, but either way the cost series is wrong across the boundary.
This is precisely why R-8.3.a requires fee rates to be a dated
`effective_from → rate` schedule rather than a constant, and why a single
"current rate" constant would have quietly corrupted every cross-period result.

## Note on verification in this environment

The session that recorded S-1 through S-4 could not reach `sec.gov`,
`finra.org`, `docs.alpaca.markets`, or `alpaca.markets` — the environment's
network egress policy blocks them. The values above come from search-result
summaries, which is why they are PROVISIONAL rather than VERIFIED.

To promote them, either:

- open those domains in the environment's network policy and re-check, or
- have the operator read each primary source and record the value, date, and
  their name in the table.

**Nothing may go live on a PROVISIONAL rate** (Phase 8 gate G8 / R-19.1.d).

## How to add a row

Check the fact against a primary source — the vendor's own documentation, the
regulator's own notice, or an API response you captured. Record the value, the
URL or endpoint, the date, and who checked it. If you learned it through the
Alpaca MCP, write the observation up in `docs/research/` (R-19.1.c) and link it
here.
