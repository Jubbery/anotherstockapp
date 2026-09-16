# anotherstockapp

A single-tenant, personal algorithmic day-trading platform. Scans the US equity market each morning,
narrows ~8,000 names to 50 to 10, and trades them intraday under an explicit, expiring, operator-granted
authorization — with live SMS/email notifications and a hard kill switch.

**Nothing is built yet.** This repository currently contains the specification.

## 👉 Start here: [`docs/MASTER_SPEC.md`](docs/MASTER_SPEC.md)

That document is the complete handoff: architecture, stack decisions and their rationale, database schema,
the three-stage scanning pipeline, the ML methodology, risk controls, and a gated eight-phase build plan.

### The shape of it

| | |
|---|---|
| **Frontend** | Next.js 15 + TypeScript on Vercel |
| **Backend** | Python 3.12 + FastAPI + asyncio on Fly.io (always-on during market hours) |
| **Database** | Supabase Postgres + Storage (Neon documented as a drop-in fallback) |
| **Broker & data** | Alpaca — paper and live, one base URL apart |
| **ML** | LightGBM, triple-barrier labelling, purged walk-forward validation |
| **Notifications** | Twilio SMS + Resend email |

### Before you write any code

Read Sections 1–4 of the spec in full, then Appendix B. Three things in particular will change what you
build if you discover them late:

1. **The base rates for retail day trading are brutal** (§2.1). The promotion gates in §9.7 exist because of
   this, they are enforced in code, and there is no override.
2. **The PDT rule was retired in June 2026** (§2.2). Do not write a $25k gate; do not treat its absence as
   safety.
3. **Investopedia's simulator has no official API** (§2.3), so the testing venue is Alpaca paper trading
   plus an in-house event-driven backtester.

### Non-negotiables

- Live trading is **Phase 8**, behind eight gates. Paper until then.
- Every order passes the risk governor. One code path, no bypass.
- The operator can halt everything from a phone in under 10 seconds, and that gets tested weekly.
- Authorization to trade always expires within 24 hours.
