# Atlas

A single-tenant algorithmic day-trading platform for one operator.

Atlas scans the liquid US equity market each morning, narrows ~8,000 symbols to 50 by deterministic
rules and to 10 by a learned ranker, trades them intraday under an authorization that expires within
24 hours, and can be halted from a phone in under ten seconds.

```
 ~8,000 symbols ──[ Stage A: rules ]──► 50 ──[ Stage B: LightGBM ]──► 10
                                                                       │
                                        [ Stage C: meta-label gate ]───┤
                                                                       ▼
                                      [ risk governor ]──► one order path ──► Alpaca
```

## Start here

**[`docs/MASTER_SPEC.md`](docs/MASTER_SPEC.md)** is the source of truth. Read Appendix B (domain primer),
then §1–§4, then §20 (the phase plan). Everything else is reference.

## Stack

Next.js 15 + TypeScript on Vercel · Python 3.12 + FastAPI + asyncio on Fly.io · Supabase Postgres +
Storage · Alpaca for brokerage and market data · LightGBM with triple-barrier labelling and purged
walk-forward validation · Twilio SMS + Resend email.

## Non-negotiables

- Live trading is **Phase 8**, behind eight gates. Everything before it runs on paper.
- Every order passes the risk governor. One code path, no bypass.
- The operator can halt everything from a phone in under 10 seconds, tested weekly.
- Authorization to trade always expires within 24 hours.

## Status

**Phase 0 built (🔴 GATE 0 still open) · Phase 1 in progress.**
Reports: [`docs/status/`](docs/status/).

242 tests · `mypy --strict` clean · 5/5 import contracts · 5 migrations applied
and constraint-tested against PostgreSQL 16.

Built so far: the `ALPACA_ENV` guard, the money/price/quantity types, the
point-in-time adjustment engine, survivorship-safe universe snapshots,
instrument identity (tickers are not primary keys), the market calendar
(half-days included), the data platform schema, and the data quality gate. Every guard has been negative-tested — a deliberate violation
introduced, the guard fired, the violation removed.

**No market data has been ingested.** The environment's network egress policy
blocks `paper-api.alpaca.markets` and `data.alpaca.markets`, so the Alpaca MCP
proof of concept (R-19.1.a) cannot run and every fee, feed, and rate-limit value
in [`docs/SOURCES.md`](docs/SOURCES.md) remains PROVISIONAL — unusable by code
that trades real money.

Open items **O-1** (data feed budget) and **O-2** (capital and maximum
acceptable loss) still block. **O-3** (equities only) and **O-5** (long-only for
v1) are resolved — see [`docs/decisions/`](docs/decisions/).

## Development

```bash
make install     # uv sync, Python 3.12
make check       # everything CI runs, except the database job
make help
```

## A word on expectations

Day trading is overwhelmingly loss-making for individual participants. This project is structured so
that the parts that tell you the truth — point-in-time data, an honest backtester, validation that
corrects for multiple testing — come first, and the parts that spend money come last, behind gates.
If the evidence at Phase 8 says the edge is not there, not going live is a successful outcome
(§1.5, R-20.9.c).
