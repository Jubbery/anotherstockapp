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

**Phase 0 — not started.** No implementation code exists yet. The specification is complete and the
open items in §21 are awaiting the operator's answers; **O-1** (data feed budget) and **O-2** (capital
and maximum acceptable loss) block Phases 1 and 6 respectively.

## A word on expectations

Day trading is overwhelmingly loss-making for individual participants. This project is structured so
that the parts that tell you the truth — point-in-time data, an honest backtester, validation that
corrects for multiple testing — come first, and the parts that spend money come last, behind gates.
If the evidence at Phase 8 says the edge is not there, not going live is a successful outcome
(§1.5, R-20.9.c).
