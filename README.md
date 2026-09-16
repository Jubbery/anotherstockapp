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
| **Notifications** | Telegram (free, primary) + Resend email; Twilio SMS optional |

### Before you write any code

Read Sections 1–4 of the spec in full, then Appendix B. Three things in particular will change what you
build if you discover them late:

1. **The base rates for retail day trading are brutal** (§2.1). The promotion gates in §9.7 exist because of
   this, they are enforced in code, and there is no override.
2. **The PDT rule was retired in June 2026** (§2.2). Do not write a $25k gate; do not treat its absence as
   safety.
3. **No Twilio A2P campaign is needed** (§13.1) — trial accounts can't register for one anyway, and
   reviews run 10–15 days. Telegram is the primary channel: free, instant, and it supports inline
   approve/reject buttons, which beats typing a code back under time pressure.

### The proof of concept comes first

Before any engine code, run the Phase 0 proof of concept through the
[Alpaca MCP server](https://github.com/alpacahq/alpaca-mcp-server) (paper keys only): pull a quote, place a
bracket order, watch it fill, close it. One conversation, no code. It validates the account, keys, and order
semantics and surfaces Alpaca's real response shapes before they get baked into a client.

### Non-negotiables

- Live trading is **Phase 8**, behind eight gates. Paper until then.
- Every order passes the risk governor. One code path, no bypass.
- The operator can halt everything from a phone in under 10 seconds, and that gets tested weekly.
- Authorization to trade always expires within 24 hours.
