# Atlas — Personal Algorithmic Day-Trading Platform
## Master Specification & Developer Handoff

| | |
|---|---|
| **Document version** | 1.0 |
| **Date** | 2026-09-16 |
| **Status** | Approved for implementation |
| **Audience** | The engineer (or Claude session) building this from zero |
| **Repository** | `Jubbery/anotherstockapp` |
| **Operator / sole user** | Jack Roberts (`jackroberts.usf@gmail.com`) |

---

### Contents

| | | | |
|---|---|---|---|
| [0. How to use this doc](#0-how-to-use-this-document) | [6. Operator authorization](#6-operator-authorization--the-with-user-permission-requirement) | [12. Funding & capital](#12-funding-capital-policy-and-cash-out) | [18. Compliance & tax](#18-compliance-legal-and-tax) |
| [1. Product vision](#1-product-vision) | [7. The Ticker Bot pipeline](#7-the-ticker-bot-pipeline) | [13. Notifications](#13-notifications) | [19. Claude tooling (MCP)](#19-claude-tooling--mcp-servers-and-plugins) |
| [**2. Reality check** ⚠](#2-reality-check--read-before-building) | [8. The backtester](#8-the-backtester) | [14. Frontend & API](#14-frontend-and-api-surface) | [**20. Build plan**](#20-build-plan) |
| [3. Architecture](#3-system-architecture) | [**9. ML methodology**](#9-machine-learning-methodology) | [15. Security & observability](#15-security-and-observability) | [21. Open decisions](#21-open-decisions-for-the-operator) |
| [4. Tech decisions](#4-technology-decisions) | [10. Execution & risk](#10-execution-and-risk-management) | [16. Testing](#16-testing) | [22. Glossary](#22-glossary) |
| [5. Data model](#5-data-model-postgres) | [11. Alpaca integration](#11-broker-and-market-data-integration--alpaca) | [17. Deployment](#17-deployment-and-scheduling) | [A. Failure modes](#appendix-a--the-ten-things-most-likely-to-sink-this-project) · [B. First tasks](#appendix-b--first-tasks-for-the-implementing-session) |

---

## 0. How to use this document

This is the single source of truth. Read **Sections 1–4 in full before writing any code** — they contain
decisions that are expensive to reverse. Then work the phase plan in Section 20 in order.

**Conventions used here:**

- **MUST / MUST NOT** — non-negotiable. Violating these breaks correctness, safety, or the law.
- **SHOULD** — strong default. Deviate only with a written reason in `docs/decisions/`.
- **MAY** — genuine latitude.
- 🔴 **HARD GATE** — a checkpoint that MUST pass before the next phase starts.

**If you are a Claude session picking this up:** do not attempt to build the whole system in one pass.
Build Phase 0, get it green, commit, and stop. Each phase has explicit acceptance criteria. The single
most common failure mode for this project is writing an execution engine before a trustworthy backtester
exists, and then trusting numbers that are wrong.

### The four non-negotiables

Everything else in this document is detail. These four are the spec:

1. **Live trading is Phase 8, behind eight gates.** Paper until then — no exceptions, no "just a small live
   test to see how it feels." (Section 20)
2. **Every order passes the risk governor. One code path, no bypass.** Enforced by a CI lint rule, not by
   discipline. (R-10.1.b)
3. **The operator can halt everything from a phone in under 10 seconds — and that gets tested weekly,
   automatically, against the real inbound path.** (R-6.10, R-16.5.a, R-13.7.g)
4. **Authorization to trade always expires within 24 hours.** There is no permanent authorization and the
   system must not offer one. (R-6.1)

If a decision you are about to make conflicts with one of these, the decision is wrong.

**Where this document is deliberately opinionated**, Section 4 records the alternatives considered and why
they were rejected. If you want to change a stack decision, read that first.

---

## 1. Product vision

A single-tenant, self-hosted investment platform for one person. It:

1. Connects to a funded brokerage account.
2. Scans the US equity market each morning and narrows ~8,000 listed names to **50 tradable candidates**.
3. Ranks those 50 down to **10** with the best modelled odds of a profitable intraday move.
4. Trades those names intraday, **only within an explicit, expiring, scoped authorization granted by the
   operator**, and pushes live notifications to the operator's phone and inbox.
5. Lets the operator flatten, halt, and withdraw at any time.

It is **not** a product for other people. See Section 18 — the moment a second person's money enters, this
becomes a regulated investment advisory business and the build changes completely.

### 1.1 Success criteria for the system

The system is a success if, after Phase 8, all of the following are true:

- It runs unattended through a full trading day without manual intervention or crash.
- Every order it places can be traced to a model decision, a feature vector, and an authorization record.
- Its live P&L tracks its paper P&L, which tracks its backtest P&L, within documented tolerances.
- The operator can kill it from a phone in under 10 seconds.
- **It has demonstrated, out-of-sample, that it beats the baselines in Section 9.6.** If it has not, the
  correct outcome is that it does not trade live. That is a successful project, not a failed one.

---

## 2. Reality check — read before building

These are not disclaimers. Each one changes a design decision downstream.

### 2.1 The base rates for retail day trading are brutal

The peer-reviewed literature is consistent across decades and countries: roughly **70–80% of active retail
day traders lose money net of costs within their first year**, and studies following traders over longer
horizons find only ~1–3% profitable across three or more years. Barber & Odean's Taiwan dataset (360k+
traders) and the 2019 Brazilian study (97% of those persisting past 300 days lost money) are the canonical
references.

**Design consequences — these are requirements, not commentary:**

- **R-2.1.a** The system MUST compute and display a "cost drag" figure on every backtest and every live day:
  total fees + modelled slippage + spread crossed, as a percentage of gross P&L. Most retail strategies are
  profitable gross and unprofitable net. You must be able to see that immediately.
- **R-2.1.b** The promotion gates in Section 9.7 MUST be enforced in code, not by human judgment. A model
  that fails them cannot be deployed to live, and the deployment path MUST refuse it.
- **R-2.1.c** Position sizing MUST start at a level where a total loss is an acceptable outcome (Section 10.4).

### 2.2 The PDT rule is gone — but that is not permission

**As of 2026 the $25,000 pattern-day-trader minimum no longer exists.** The SEC approved FINRA's amendments
to Rule 4210 on 2026-04-14; the change took effect 2026-06-04, retiring both the "pattern day trader"
designation and the $25k minimum equity requirement. Alpaca implemented its replacement **Intraday Margin
Framework** on the same date, and lifted existing PDT restrictions on customer accounts.

What replaced it is **dynamic, real-time intraday margin** based on actual exposure. Accounts below $2,000
equity can day trade but only unleveraged — cash available only, no margin extension.

**Design consequences:**

- **R-2.2.a** The engine MUST NOT contain a hardcoded day-trade counter or a $25k gate. That logic is dead.
- **R-2.2.b** The engine MUST read buying power from the broker before every order and MUST treat the
  broker's response as authoritative. Under a dynamic intraday margin regime, available buying power can
  change *during the session* as exposure changes. Do not cache it across orders.
- **R-2.2.c** Brokers have until 2027-10-20 to fully implement the new framework, so behaviour may shift
  during this project's life. Margin/buying-power handling MUST be isolated in one module
  (`engine/broker/margin.py`) so a regime change is a single-file edit.
- **R-2.2.d** The absence of a regulatory floor removes a guardrail that was protecting undercapitalized
  traders. The system's *own* risk limits (Section 10) are now the only thing standing between the operator
  and a fast account. Treat them as safety-critical code.

### 2.3 Investopedia's simulator cannot be the testing venue

The brief named Investopedia's simulator for proof-of-concept and model training. **Investopedia publishes
no official API.** Everything that exists is community Python packages (`dchrostowski/investopedia_simulator_api`,
`kirkthaker/investopedia-trading-api`, and forks) that screen-scrape the site with session cookies. They
break whenever the site's markup changes, several are years stale, and they would put the operator's
credentials in the app's secret store for no gain.

More fundamentally, its fills are not a realistic model of execution — which is exactly the thing that
decides whether an intraday strategy is profitable.

**Decision: substitute a two-layer simulation stack.** This satisfies the original intent (safe proof of
concept and model training with no capital at risk) with far better fidelity:

| Layer | Purpose | Implementation |
|---|---|---|
| **L1 — Event-driven backtester** | Model training, hyperparameter search, walk-forward validation | Built in-house (Section 8). Runs on historical bars, models spread/slippage/fees explicitly. |
| **L2 — Alpaca Paper Trading** | Live-market proof of concept, integration testing, shadow mode | Alpaca's paper API. Same endpoints, same auth model, same order semantics as live — one base-URL change to go live. No real money, no real securities. |

**R-2.3.a** L2 MUST be the *only* trading venue until 🔴 HARD GATE 8. Live trading is Phase 8.
**R-2.3.b** The Investopedia scrapers MUST NOT be a dependency. If the operator wants a leaderboard-style
sim for fun, that is a separate, optional, clearly-isolated read-only integration — not part of this system.

### 2.4 Free market data will lie to you

Alpaca's free data tier gives 15-minute delayed REST data and a **real-time WebSocket carrying IEX only**,
at 200 requests/minute. IEX is roughly 2–3% of consolidated US equity volume.

This matters more than it sounds. Volume, VWAP, relative volume, and spread computed from IEX alone are
**systematically wrong**, and those are precisely the features the Stage A scanner depends on. A model
trained on IEX-derived features and deployed against SIP-derived features will silently degrade.

**Design consequences:**

- **R-2.4.a** Development and unit testing MAY use the free tier.
- **R-2.4.b** Any model training run, backtest of record, or paper-trading evaluation MUST use full SIP
  consolidated data. Budget **$99/month for Alpaca Algo Trader Plus** (full SIP real-time, OPRA options,
  10,000 rpm) as a hard prerequisite of Phase 4.
- **R-2.4.c** Every bar row in the database MUST record its `feed` provenance (`iex` | `sip` | `delayed`).
  Training jobs MUST filter to a single feed and MUST fail loudly on a mixed-provenance dataset.

### 2.5 What the machine learning can and cannot do

The brief's premise — "rule-based systems have failed time and time again, so train a model" — is half
right, and the half that is wrong will cost you months if uncorrected.

Rule-based systems fail as **alpha generators**. They do not fail as **filters and constraints**. A rule
that says "do not trade anything with an average spread above 15bps" is not a prediction; it is a
statement about tradability, and it is correct regardless of regime.

**Therefore the pipeline is deliberately hybrid** (Section 7): deterministic rules do the *filtering*
(8,000 → 50), a learned model does the *ranking* (50 → 10), and a second learned model does *execution
gating* (trade / skip / size). Trying to make one model do all three is the most common way these projects
fail — the signal-to-noise ratio in intraday equity returns is far too low to learn liquidity constraints
and alpha simultaneously from the same objective.

**R-2.5.a** Do not replace the Stage A rules with a model "to be consistent." They are doing a different job.

---

## 3. System architecture

```
                         ┌───────────────────────────────────────┐
                         │          OPERATOR (one human)          │
                         │   Browser (Next.js)    Phone (SMS)     │
                         └───────┬───────────────────────┬────────┘
                                 │ HTTPS/SSE             │ Telegram
                    ┌────────────▼───────────┐    ┌──────▼─────────┐
                    │   web  (Vercel)        │    │ Telegram/Resend │
                    │   Next.js 15 + TS      │    │ (+ optional SMS)│
                    │   Supabase Auth + TOTP │    │ out, replies in │
                    └────────────┬───────────┘    └──────▲─────────┘
                                 │ REST + SSE            │
    ═══════════════════════ Fly.io (always-on) ══════════╪═══════════════════
                                 │                       │
                    ┌────────────▼───────────────────────┴───────────┐
                    │  api   — FastAPI (24/7)                        │
                    │  authz, control plane, SSE fan-out, webhooks   │
                    └──┬────────────────┬──────────────────┬─────────┘
                       │                │                  │
         ┌─────────────▼──────┐  ┌──────▼─────────┐  ┌─────▼────────────┐
         │ engine (mkt hours) │  │ worker (cron)  │  │  notifier        │
         │ ─────────────────  │  │ ────────────── │  │  ──────────────  │
         │ · WS market data   │  │ · nightly bar  │  │ · event → SMS    │
         │ · Stage C model    │  │   ingest       │  │ · throttle/dedupe│
         │ · order state m/c  │  │ · Stage A scan │  │ · delivery log   │
         │ · risk governor    │  │ · Stage B rank │  └──────────────────┘
         │ · broker reconcile │  │ · model train  │
         └─────────┬──────────┘  └──────┬─────────┘
                   │                    │
      ┌────────────▼────────────────────▼──────────────────────────┐
      │  Redis (Upstash)  — hot state, locks, streams, idempotency │
      └────────────┬───────────────────────────────────────────────┘
                   │
      ┌───────────────────────────────────────────────────────────┐
      │  Supabase  (one vendor — see 4.3)                         │
      │  ├ Postgres : orders, positions, decisions, authz, audit, │
      │  │            model registry, trailing-30d bars           │
      │  └ Storage  : Parquet research corpus, model artifacts,   │
      │               backtest outputs   (S3-compatible → DuckDB) │
      └───────────────────────────────────────────────────────────┘
                   │
      ┌────────────▼───────────────────────────────────────────────┐
      │  Alpaca:  Market Data API (SIP)  +  Trading API (paper→live)│
      └────────────────────────────────────────────────────────────┘
```

### 3.1 Process responsibilities

| Process | Lifetime | Responsibility | Restart safety |
|---|---|---|---|
| `web` | Serverless | UI only. Holds no trading state. | Trivially restartable |
| `api` | 24/7, 1 instance | Control plane, auth, SSE, inbound notification webhooks. Never places orders directly. | Stateless — restart freely |
| `engine` | 08:00–16:30 ET weekdays, **exactly 1 instance** | The only process permitted to send orders. | MUST rebuild state from broker + DB on boot (Section 10.7) |
| `worker` | Scheduled | Ingest, scan, rank, train, report. | Idempotent jobs, safe to re-run |
| `notifier` | 24/7 | Outbound messages. | At-least-once with dedupe keys |

**R-3.1.a** `engine` MUST hold a Redis-based singleton lease (`engine:leader`, 30s TTL, renewed every 10s).
It MUST NOT place any order without a valid lease. Two engines running simultaneously is the single most
dangerous failure mode in this system — it produces duplicate orders and unbounded position size.

**R-3.1.b** Only `engine` may call broker order endpoints. `api` requests trading actions by writing an
intent to Redis Streams; `engine` consumes it. This keeps one writer for order state.

---

## 4. Technology decisions

### 4.1 The stack

| Layer | Choice | Version target |
|---|---|---|
| Frontend | **Next.js (App Router) + TypeScript**, Tailwind, shadcn/ui, TanStack Query, `lightweight-charts` | Next 15.x, TS 5.x, strict |
| Frontend host | **Vercel** | — |
| Backend | **Python 3.12 + FastAPI + asyncio**, Pydantic v2, SQLAlchemy 2.0, Alembic | — |
| Backend host | **Fly.io** — persistent Machines, `fly.toml` per process group | — |
| Database | **Supabase Postgres** (see 4.3; Neon is the documented drop-in fallback) | PG 16+ |
| Research store | **Supabase Storage** (S3-compatible), Parquet + DuckDB | — |
| Cache / bus | **Upstash Redis** (streams, locks, hot state) | — |
| Market data + broker | **Alpaca** — Market Data API (SIP) + Trading API. **Paper and live are the same integration**, one base URL apart | — |
| Dev/ops copilot | **Alpaca official MCP server** (`alpacahq/alpaca-mcp-server`) — research & ops only, never the hot path (Section 19) | v2.3.1+ |
| ML | **LightGBM** primary, scikit-learn, Polars, PyArrow; MLflow for the model registry | — |
| Notifications | **Telegram Bot API** (primary, free, bidirectional) + **Resend** (email); Twilio SMS optional for `critical` — **no A2P campaign** (Section 13) | — |
| Auth | **Supabase Auth** (email magic link) + mandatory **TOTP/MFA**, single-email allowlist | — |
| Observability | OpenTelemetry → **Grafana Cloud** (free tier); Sentry for errors | — |
| CI | GitHub Actions | — |

### 4.2 Why a Python backend, given a TypeScript frontend

This is the decision most likely to be second-guessed, so the reasoning is recorded here.

The trading engine's hard dependency is the quantitative ecosystem: LightGBM, scikit-learn, Polars/pandas,
PyArrow, statsmodels, and the `mlfinlab`-lineage techniques in Section 9. The TypeScript equivalents are
immature and would consume months reimplementing purged cross-validation and triple-barrier labelling.

The cost of a polyglot repo is one well-specified HTTP/SSE boundary, which we need anyway because the
frontend is serverless and the engine is not. That is a good trade.

**Rejected alternatives:**

| Alternative | Why rejected |
|---|---|
| All-TypeScript (Node engine) | Would require reimplementing the ML stack. The frontend/backend language symmetry is not worth it. |
| Next.js API routes / Vercel Functions as the backend | **Fatal mismatch.** The engine must hold a WebSocket to the market data feed for 6.5 continuous hours, maintain in-memory order state, and act on a sub-second loop. Serverless functions are request-scoped, time-limited, and horizontally scaled — all three are wrong here. Vercel hosts the UI only. |
| Rust / Go engine | Correct for sub-millisecond HFT. This system's decision cadence is seconds-to-minutes; Python is fast enough and the ML ecosystem dominates. |
| AWS ECS/Fargate | Works, more operational surface than Fly.io for one always-on process. Revisit only if Fly.io proves unreliable. |
| Neon (the operator's original pick) | Excellent product; its branching is genuinely useful for reproducible research. But it is *only* a database, so it leaves object storage and auth as two more vendors to wire up. It remains a **supported fallback** — swapping back is a connection-string change (Section 4.3.1). |
| PlanetScale | MySQL-lineage; we want Postgres for `numeric`, partitioning, and the Postgres extension ecosystem. |

### 4.3 Storage: one vendor, split by access pattern

**The problem is volume, not vendor.** Minute bars for ~8,000 symbols × 390 bars/day × 252 days ≈
**786M rows/year**. That is the wrong shape for any serverless OLTP Postgres that you also pay for by
compute-hour — and it is the reason this section exists at all.

Neon was the operator's original pick and it is a good database. The issue is that it is *only* a database:
you still need object storage for the Parquet research corpus and a separate auth provider, which is three
vendors and three sets of credentials for a single-user app.

**Decision: use Supabase.** It collapses those three into one product — Postgres, S3-compatible Storage, and
Auth — with one dashboard and one set of keys. Nothing about the application code is Supabase-specific: it
is stock Postgres behind SQLAlchemy, and the storage client speaks S3.

| Data | Store | Rationale |
|---|---|---|
| Orders, positions, decisions, authorizations, notifications, audit log, model registry, **trailing 30 days of bars** | **Supabase Postgres**, bars in a daily-partitioned table managed by `pg_partman` | Transactional, queried by the app, small enough to stay fast |
| Full historical bar corpus, quote archives, feature matrices, backtest outputs, model artifacts | **Supabase Storage** as Parquet, keyed `feed=/symbol_bucket=/date=`, queried with **DuckDB** over the S3 protocol | Columnar, cheap, 10–100× faster for training scans, zero database compute cost |
| Hot in-session state (last price, open orders, risk counters, locks, leases) | **Upstash Redis** | Sub-millisecond, ephemeral by design |

**R-4.3.a** Training jobs MUST read Parquet from Storage via DuckDB, never from Postgres. A training job that
scans Postgres will be slow, expensive, and will eventually take the database down mid-session.
**R-4.3.b** The nightly ingest MUST write bars to **both** Postgres (trailing window) and Storage (permanent),
and MUST verify row-count parity between them before marking the session ingested.
**R-4.3.c** Use the **Pro plan ($25/mo), not the free tier.** Free Supabase projects are **paused after one
week of inactivity** — a database that suspends itself is disqualifying for a system that must be awake at
09:30 ET. Do not rely on the free tier past local development.
**R-4.3.d** All database access MUST go through SQLAlchemy against a plain `DATABASE_URL`. Do NOT use
`supabase-js`/`supabase-py` client libraries for application data, and do NOT put business logic in RLS
policies or Postgres functions. This keeps the fallback in 4.3.1 below a genuine one-line swap.

#### 4.3.1 Fallback: switching back to Neon

If Supabase disappoints, the exit is deliberately cheap. Because of R-4.3.d:

1. Point `DATABASE_URL` at Neon. Alembic migrations run unchanged.
2. Point the storage client at Cloudflare R2 (also S3-compatible) — an endpoint and credential change in
   `common/storage.py`.
3. Replace Supabase Auth with Auth.js + TOTP in `web/` — the only real work, roughly a day, and it touches
   no backend code because the API trusts a verified JWT with a single allowlisted subject either way.

Record the move as an ADR in `docs/decisions/` if you make it.

#### 4.3.2 If you want a time-series-native database instead

**TigerData** (formerly Timescale; renamed June 2025) is the strongest technical fit for bar data —
real hypertables, columnstore compression, and continuous aggregates, all of which are *unavailable* on
Neon, which ships only the Apache-2 edition of `timescaledb` without compression or tiered storage.

It is not the recommendation here only because it does not reduce the vendor count, and the
Postgres-plus-Parquet split above already solves the volume problem. If bar queries become the bottleneck,
adopting TigerData for the market-data tables is a reasonable Phase 5+ change; write an ADR.

### 4.4 Repository layout

```
anotherstockapp/
├── docs/
│   ├── MASTER_SPEC.md          ← this file
│   ├── decisions/              ← ADRs; one file per deviation from this spec
│   └── runbooks/               ← incident procedures (Section 15.4)
├── web/                        ← Next.js + TypeScript
│   ├── app/                    ← App Router
│   ├── components/
│   ├── lib/api/                ← generated client from OpenAPI — do not hand-write
│   └── types/generated/        ← generated from backend Pydantic schemas
├── services/
│   ├── common/                 ← shared: models, config, db, telemetry, broker client
│   ├── api/                    ← FastAPI control plane
│   ├── engine/                 ← trading engine (the safety-critical code)
│   │   ├── strategy/
│   │   ├── execution/
│   │   ├── risk/               ← risk governor — highest test coverage bar
│   │   └── broker/
│   ├── worker/                 ← ingest, scan, rank, train, report
│   ├── notifier/
│   └── research/
│       ├── backtest/           ← event-driven simulator
│       ├── features/           ← feature library (shared with engine — see R-4.4.a)
│       └── models/
├── db/migrations/              ← Alembic
├── infra/                      ← fly.toml, Dockerfiles, GH Actions
└── tests/
    ├── unit/ integration/ backtest_golden/ chaos/
```

**R-4.4.a** Feature computation code MUST be imported by both `research/backtest` and `engine`. It MUST NOT
be duplicated. A feature that is computed differently in training and live is called *training/serving skew*
and it is the highest-probability silent-failure mode in this entire system.

### 4.5 Coding standards

- Python: `ruff` (lint + format), `mypy --strict` on `services/`, `pytest`. All money as `Decimal`, never
  `float`. All timestamps timezone-aware UTC in storage; convert to `America/New_York` only at display.
- TypeScript: `strict: true`, `biome` or ESLint+Prettier. No `any` in `web/lib` or `web/types`.
- **R-4.5.a** The API contract is generated: FastAPI emits OpenAPI → `openapi-typescript` generates
  `web/types/generated/`. CI MUST fail if generated files are stale.
- **R-4.5.b** Every database write that changes money, position, or authorization state MUST be inside a
  transaction that also writes an `audit_log` row. Enforce with a repository-layer helper, not by convention.

---

## 5. Data model (Postgres)

Abbreviated DDL — the shape and the constraints matter more than the exact column list. All tables carry
`created_at timestamptz NOT NULL DEFAULT now()`.

```sql
-- ─── Reference ────────────────────────────────────────────────────────────
CREATE TABLE symbols (
  symbol            text PRIMARY KEY,
  name              text NOT NULL,
  exchange          text NOT NULL,
  asset_class       text NOT NULL DEFAULT 'us_equity',
  tradable          boolean NOT NULL,
  shortable         boolean NOT NULL,
  easy_to_borrow    boolean NOT NULL,
  fractionable      boolean NOT NULL,
  marginable        boolean NOT NULL,
  delisted_at       date,                        -- CRITICAL: never delete rows (Section 9.5)
  updated_at        timestamptz NOT NULL
);

CREATE TABLE market_calendar (
  session_date      date PRIMARY KEY,
  open_at           timestamptz NOT NULL,
  close_at          timestamptz NOT NULL,
  is_early_close    boolean NOT NULL DEFAULT false
);

-- ─── Market data (trailing window only; full history lives in object storage) ──
CREATE TABLE bars_1m (
  symbol        text        NOT NULL,
  ts            timestamptz NOT NULL,           -- bar OPEN time, UTC
  open          numeric(18,6) NOT NULL,
  high          numeric(18,6) NOT NULL,
  low           numeric(18,6) NOT NULL,
  close         numeric(18,6) NOT NULL,
  volume        bigint      NOT NULL,
  trade_count   integer     NOT NULL,
  vwap          numeric(18,6),
  feed          text        NOT NULL,            -- 'sip' | 'iex' | 'delayed'  (R-2.4.c)
  adjusted      boolean     NOT NULL DEFAULT false,
  PRIMARY KEY (symbol, ts, feed)
) PARTITION BY RANGE (ts);                       -- managed by pg_partman, daily

-- ─── Pipeline output ──────────────────────────────────────────────────────
CREATE TABLE scan_runs (
  id              uuid PRIMARY KEY,
  session_date    date NOT NULL,
  stage           text NOT NULL,                 -- 'A_universe' | 'B_rank'
  started_at      timestamptz NOT NULL,
  finished_at     timestamptz,
  status          text NOT NULL,                 -- 'running'|'ok'|'failed'
  universe_size   integer,
  model_version   text REFERENCES model_versions(version),
  params          jsonb NOT NULL,                -- exact config used — reproducibility
  error           text
);

CREATE TABLE candidates (
  id              uuid PRIMARY KEY,
  scan_run_id     uuid NOT NULL REFERENCES scan_runs(id) ON DELETE CASCADE,
  session_date    date NOT NULL,
  symbol          text NOT NULL REFERENCES symbols(symbol),
  stage           text NOT NULL,                 -- 'A' (the 50) | 'B' (the 10)
  rank            integer NOT NULL,
  score           numeric(10,6),                 -- model probability, stage B only
  features        jsonb NOT NULL,                -- FULL vector — required for explainability + audit
  rejected_reason text,                          -- why a stage-A name did not make stage B
  UNIQUE (scan_run_id, symbol)
);

-- ─── Authorization: the human-in-the-loop record ──────────────────────────
CREATE TABLE trading_authorizations (
  id                    uuid PRIMARY KEY,
  granted_at            timestamptz NOT NULL,
  granted_via           text NOT NULL,           -- 'web' | 'sms'
  expires_at            timestamptz NOT NULL,    -- MUST be set, max 24h; see R-6.1
  mode                  text NOT NULL,           -- 'manual'|'semi'|'auto'
  max_notional          numeric(18,2) NOT NULL,
  max_daily_loss        numeric(18,2) NOT NULL,
  max_position_count    integer NOT NULL,
  allowed_symbols       text[],                  -- NULL = the stage-B ten
  revoked_at            timestamptz,
  revoked_reason        text,
  operator_ip           inet,
  operator_user_agent   text
);

-- ─── Trading ──────────────────────────────────────────────────────────────
CREATE TABLE decisions (
  id                uuid PRIMARY KEY,
  session_date      date NOT NULL,
  symbol            text NOT NULL,
  decided_at        timestamptz NOT NULL,
  action            text NOT NULL,               -- 'enter_long'|'enter_short'|'exit'|'skip'
  model_version     text NOT NULL REFERENCES model_versions(version),
  features          jsonb NOT NULL,              -- the EXACT vector fed to the model
  raw_score         numeric(10,6) NOT NULL,
  meta_score        numeric(10,6),               -- meta-label confidence (Section 9.4)
  size_shares       integer,
  reason            text NOT NULL,               -- human-readable, shown in UI + SMS
  risk_checks       jsonb NOT NULL,              -- every check + pass/fail
  authorization_id  uuid REFERENCES trading_authorizations(id),
  suppressed_by     text                         -- non-null if risk governor blocked it
);

CREATE TABLE orders (
  id                  uuid PRIMARY KEY,
  broker_order_id     text UNIQUE,               -- NULL until broker ACKs
  client_order_id     text UNIQUE NOT NULL,      -- OUR idempotency key (R-10.5.a)
  decision_id         uuid REFERENCES decisions(id),
  symbol              text NOT NULL,
  side                text NOT NULL,
  order_type          text NOT NULL,
  time_in_force       text NOT NULL,
  qty                 integer NOT NULL,
  limit_price         numeric(18,6),
  stop_price          numeric(18,6),
  status              text NOT NULL,
  filled_qty          integer NOT NULL DEFAULT 0,
  filled_avg_price    numeric(18,6),
  submitted_at        timestamptz,
  filled_at           timestamptz,
  canceled_at         timestamptz,
  bracket_parent_id   uuid REFERENCES orders(id),
  raw_broker_payload  jsonb,                     -- last full response, for forensics
  updated_at          timestamptz NOT NULL
);

CREATE TABLE fills (
  id                uuid PRIMARY KEY,
  order_id          uuid NOT NULL REFERENCES orders(id),
  broker_fill_id    text UNIQUE NOT NULL,
  qty               integer NOT NULL,
  price             numeric(18,6) NOT NULL,
  filled_at         timestamptz NOT NULL,
  fees              numeric(18,6) NOT NULL DEFAULT 0
);

CREATE TABLE positions_eod (                     -- daily snapshot, reconciled against broker
  session_date      date NOT NULL,
  symbol            text NOT NULL,
  qty               integer NOT NULL,
  avg_entry_price   numeric(18,6) NOT NULL,
  market_value      numeric(18,2) NOT NULL,
  realized_pnl      numeric(18,2) NOT NULL,
  unrealized_pnl    numeric(18,2) NOT NULL,
  PRIMARY KEY (session_date, symbol)
);

CREATE TABLE account_snapshots (
  taken_at          timestamptz PRIMARY KEY,
  equity            numeric(18,2) NOT NULL,
  cash              numeric(18,2) NOT NULL,
  buying_power      numeric(18,2) NOT NULL,
  maintenance_margin numeric(18,2),
  source            text NOT NULL                -- 'broker' — never computed locally
);

-- ─── ML ───────────────────────────────────────────────────────────────────
CREATE TABLE model_versions (
  version           text PRIMARY KEY,            -- e.g. 'stageB-2026.09.16-a3f21c'
  stage             text NOT NULL,               -- 'B_rank' | 'C_entry' | 'C_meta'
  algorithm         text NOT NULL,
  trained_at        timestamptz NOT NULL,
  train_start       date NOT NULL,
  train_end         date NOT NULL,
  oos_start         date NOT NULL,
  oos_end           date NOT NULL,
  feature_list      jsonb NOT NULL,              -- ordered; live inference MUST match exactly
  hyperparams       jsonb NOT NULL,
  metrics           jsonb NOT NULL,              -- all of Section 9.7
  artifact_uri      text NOT NULL,               -- object-storage path
  git_sha           text NOT NULL,
  data_snapshot_id  text NOT NULL,               -- storage manifest hash — reproducibility
  status            text NOT NULL,               -- 'candidate'|'shadow'|'paper'|'live'|'retired'
  promoted_at       timestamptz,
  promotion_gate_results jsonb                   -- proof it passed Section 9.7 (R-2.1.b)
);

-- ─── Ops ──────────────────────────────────────────────────────────────────
CREATE TABLE notifications (
  id            uuid PRIMARY KEY,
  dedupe_key    text UNIQUE NOT NULL,            -- at-least-once → exactly-once-ish
  channel       text NOT NULL,                   -- 'sms'|'email'
  event_type    text NOT NULL,
  severity      text NOT NULL,                   -- 'info'|'warn'|'critical'
  body          text NOT NULL,
  sent_at       timestamptz,
  provider_id   text,
  status        text NOT NULL,                   -- 'queued'|'sent'|'delivered'|'failed'
  error         text
);

CREATE TABLE risk_events (
  id            uuid PRIMARY KEY,
  occurred_at   timestamptz NOT NULL,
  rule          text NOT NULL,
  severity      text NOT NULL,
  action_taken  text NOT NULL,                   -- 'blocked_order'|'halted_session'|'flattened_all'
  context       jsonb NOT NULL
);

CREATE TABLE audit_log (                         -- append-only; no UPDATE, no DELETE
  id            bigserial PRIMARY KEY,
  occurred_at   timestamptz NOT NULL DEFAULT now(),
  actor         text NOT NULL,                   -- 'operator:<email>'|'system:engine'|'system:worker'
  action        text NOT NULL,
  entity_type   text NOT NULL,
  entity_id     text,
  before        jsonb,
  after         jsonb,
  request_id    text
);
```

**R-5.a** `symbols` rows MUST NEVER be deleted. Delisted names get `delisted_at` set. Deleting them creates
**survivorship bias** — the backtest would only ever see companies that still exist, which are
disproportionately the ones that did well. This single mistake can turn a losing strategy into a beautiful
backtest.

**R-5.b** `audit_log` MUST be append-only. Enforce with a `BEFORE UPDATE OR DELETE` trigger that raises.

**R-5.c** `decisions.features` and `candidates.features` store the full vector. They are large and that is
fine — without them you cannot explain a trade after the fact, and every serious post-mortem needs them.

---

## 6. Operator authorization — the "with user permission" requirement

Requirement 4 of the brief says the bot trades *with user permission*. That phrase has to become a
concrete, enforceable, auditable object, or it degrades into a checkbox that was ticked once in March.

### 6.1 The authorization object

Trading is permitted only while a **non-revoked, unexpired `trading_authorizations` row** exists. It carries
a mode, hard limits, and an expiry. It is the engine's licence to operate.

| Mode | Behaviour | Use when |
|---|---|---|
| `manual` | Every entry requires explicit operator approval before the order is sent. Bot proposes; human disposes. | Phases 5–7, and any time confidence is low |
| `semi` | Operator approves the **morning plan** (the ten names + parameters) once. The engine then trades only those names, autonomously, within the envelope. Exits are always autonomous. | The intended steady state |
| `auto` | Engine trades within the envelope with no per-session approval. | Only after a long, documented live track record |

### 6.2 Rules

- **R-6.1** `expires_at` MUST be set on every authorization and MUST NOT exceed **24 hours** from grant.
  There is no permanent authorization, and the system MUST NOT offer one. A bot with open-ended permission
  to trade the operator's money is the scenario every safeguard in this document exists to prevent.
- **R-6.2** The engine MUST re-read the authorization from the database (not cache) before every order and
  MUST refuse to trade on expiry, revocation, or absence. Refusal is not an error — it is normal operation.
- **R-6.3** `max_notional`, `max_daily_loss`, and `max_position_count` are MANDATORY and MUST be enforced by
  the risk governor (Section 10), independently of any model output.
- **R-6.4** Revocation MUST take effect within **5 seconds**. Implementation: the engine subscribes to a
  Redis pub/sub channel `authz:revoked` *and* polls the DB every 5s as a backstop. Belt and braces, because
  pub/sub can silently drop.
- **R-6.5** Revocation MUST trigger the configured flatten policy (Section 10.6) — cancel all open orders,
  then close or hold positions per the operator's chosen setting. This choice MUST be made at grant time and
  stored on the authorization, not decided during an emergency.
- **R-6.6** Granting, modifying, and revoking authorization MUST each write an `audit_log` row capturing IP,
  user agent, and channel.

### 6.3 Granting

Web: an explicit form — mode, notional cap, daily loss cap, expiry, flatten policy — behind a **fresh TOTP
challenge** even if the session is already authenticated. Re-authentication for money-moving actions.

Messaging: the engine may request approval for a specific action by pushing a prompt to the operator's
phone. On Telegram (the primary channel) this is an inline **Approve / Reject** button pair bound to one
`decision_id`; over SMS, if enabled, it is a reply of `YES <code>`. Both are handled by webhooks on `api`.
See Section 13.6 for the channel design and its security rules.

- **R-6.7** SMS approval codes MUST be single-use, MUST expire in **10 minutes**, and MUST be bound to a
  specific `decision_id`. A generic "YES" MUST NOT authorize anything.
- **R-6.8** Inbound webhooks MUST be authenticated — Telegram via its secret-token header, Twilio via the
  `X-Twilio-Signature` header validated against the auth token — on every
  request. An unsigned or mis-signed request MUST be rejected with 403. Without this, anyone who learns the
  webhook URL can approve trades. This is the single most security-critical endpoint in the system.
- **R-6.9** SMS MUST NOT be able to *grant* a new authorization or *raise* a limit. It may only approve a
  specific pending action within an existing authorization, or **revoke** (see 6.4). Escalation of privilege
  over an unauthenticated channel is not acceptable.

### 6.4 The kill switch

- **R-6.10** The operator MUST be able to halt everything from a phone in **under 10 seconds**. Texting
  `/halt` to the Telegram bot (or `STOP` to the SMS number, if enabled) MUST immediately revoke all active
  authorizations and trigger the flatten
  policy. `STOP` MUST NOT require a code — the failure mode of an unwanted halt is trivial; the failure mode
  of a halt that did not work is not.
- **R-6.11** The web UI MUST show a persistent, always-visible **HALT** control on every page.
- **R-6.12** The kill switch MUST be tested on a schedule (Section 16.5). An untested emergency stop is not
  an emergency stop.

---

## 7. The Ticker Bot pipeline

Three stages, deliberately different in kind. See Section 2.5 for why this is hybrid rather than one model.

```
  ~8,000 US equities
        │
        │  STAGE A — deterministic tradability filter        (worker, 08:15 ET)
        │  liquidity · price · spread · volatility · relative volume · catalysts
        ▼
     50 candidates          → stored in `candidates` (stage 'A')
        │
        │  STAGE B — learned ranker                          (worker, 09:20 ET)
        │  LightGBM → P(favourable intraday excursion)
        ▼
     10 names               → stored in `candidates` (stage 'B')
        │
        │  ── OPERATOR APPROVES THE PLAN (mode=semi) ──      (09:25 ET)
        ▼
  STAGE C — intraday entry/exit + meta-labelling             (engine, 09:30–15:55 ET)
        │  per-bar signal · meta-model sizes or vetoes · risk governor
        ▼
     orders → broker
```

### 7.1 Stage A — universe → 50 (deterministic)

Runs at **08:15 ET** on `worker`, before the open, using previous-close data plus premarket.

Filters, applied in order (each configurable; defaults below are starting points, not gospel):

| Filter | Default | Why |
|---|---|---|
| Exchange | NASDAQ / NYSE / ARCA listed | Excludes OTC — wider spreads, thinner books, worse data |
| Price | $5.00 ≤ close ≤ $500 | Below $5: penny-stock dynamics, often hard to borrow. Above $500: share granularity hurts sizing |
| 20-day average dollar volume | ≥ $20,000,000 | **The single most important filter.** Liquidity is what lets you exit |
| Median spread (prev. session) | ≤ 15 bps | You pay this twice per round trip. It is a direct tax on the strategy |
| ATR(14) as % of price | 1.5% ≤ ATR% ≤ 12% | Below: no intraday range to capture. Above: gap/halt risk dominates |
| Market cap | ≥ $300M | Excludes microcaps prone to manipulation |
| Tradable / not halted | via broker asset API | — |
| Corporate action today | exclude splits, and reverse splits | Price series discontinuities corrupt features |
| Relative volume (premarket vs 20d avg premarket) | ≥ 1.5× | Proxy for "something is happening today" |

Then **rank the survivors by a composite tradability score** and take the top 50:

```
score_A = 0.35·z(relative_volume)
        + 0.25·z(|overnight_gap| capped at 8%)
        + 0.20·z(log dollar_volume)
        + 0.20·z(ATR%)
        − 0.30·z(spread_bps)
```

- **R-7.1.a** Stage A MUST be pure and deterministic: same inputs → same 50, always. No randomness, no
  wall-clock dependence beyond the session date. This is what makes it replayable in the backtester.
- **R-7.1.b** Stage A MUST write every rejected symbol's reason to `candidates.rejected_reason` when it
  reached the ranking round. You need to see what the funnel is throwing away.
- **R-7.1.c** If fewer than 20 names survive, the day MUST be marked `low_opportunity` and the engine SHOULD
  NOT trade. A thin market is not an invitation to loosen filters. **The system must be comfortable doing
  nothing** — most retail losses come from trading when there was nothing to trade.
- **R-7.1.d** All thresholds MUST live in a versioned config object persisted to `scan_runs.params`.
  A backtest whose parameters you cannot reconstruct is worthless.

### 7.2 Stage B — 50 → 10 (learned ranker)

Runs at **09:20 ET**, after premarket has developed.

- **Model:** LightGBM binary classifier (`objective=binary`), **not** a regressor on returns. Predicting the
  *sign and reliability* of a move is a better-posed problem than predicting its magnitude, which is
  dominated by noise.
- **Target:** `P(the triple-barrier label for this symbol today is a win)` — see Section 9.3.
- **Output:** calibrated probability (isotonic or Platt on a held-out slice — raw LightGBM scores are not
  probabilities and MUST NOT be treated as such).
- **Selection:** top 10 by calibrated probability, subject to the diversification constraints below.

**Diversification constraints (hard, applied after ranking):**

- **R-7.2.a** No more than **3** of the 10 from the same GICS sector. Ten names that move together is one
  position with extra commission.
- **R-7.2.b** Drop any name whose 20-day return correlation with an already-selected name exceeds **0.80**.
- **R-7.2.c** If fewer than 10 names clear the minimum calibrated probability threshold (default **0.55**),
  return fewer. **Returning exactly 10 every day is a bug, not a feature.** The brief says "top 10"; the
  correct reading is "up to 10, only those that qualify."

### 7.3 Stage C — intraday execution signal

Runs continuously on `engine`, 09:30–15:55 ET, on 1-minute bars for the selected names only.

Two models in series (this is **meta-labelling**, Section 9.4):

1. **Primary model** — emits a directional signal per bar: long / short / flat.
2. **Meta model** — given that the primary says "trade", predicts P(this specific trade wins). It can only
   **veto or size down**, never flip direction or size up. This separation is what makes the primary's
   recall problem and the precision problem independently tunable.

- **R-7.3.a** Entries MUST NOT be taken in the first **5 minutes** (09:30–09:35). The open is the least
  predictable and widest-spread period of the day; the training data there is dominated by noise.
- **R-7.3.b** No new entries after **15:30 ET**.
- **R-7.3.c** All positions MUST be flat by **15:55 ET**, enforced by a hard timer independent of any model
  (Section 10.6). This is a day-trading system; carrying overnight risk is out of scope and the strategy was
  never validated for it.
- **R-7.3.d** Every entry MUST be submitted as a **bracket order** (parent + take-profit + stop-loss) so that
  protection exists broker-side. If the engine dies the instant after a fill, the stop must still be live.

---

## 8. The backtester

🔴 **HARD GATE:** No model may be trained, and no strategy evaluated, before the backtester passes its golden
tests (Section 16.3). Everything downstream inherits its errors.

### 8.1 It must be event-driven, not vectorised

A vectorised backtest (pandas over a whole price series) is fast, easy, and will lie to you about intraday
strategies — it makes look-ahead trivially easy to introduce and cannot model partial fills, queue position,
or order rejection.

Build a loop that replays bars in time order and knows nothing about the future:

```python
for bar in replay(session_date, symbols, feed="sip"):
    clock.advance(bar.ts)
    portfolio.mark(bar)              # mark-to-market at the bar just closed
    sim_broker.process_open_orders(bar)   # fills resolved BEFORE new signals
    features = feature_lib.update(bar)    # same code as live (R-4.4.a)
    signal = strategy.on_bar(bar, features)
    if signal:
        sim_broker.submit(risk.check(signal))
```

### 8.2 Non-negotiable correctness rules

- **R-8.2.a — No look-ahead.** A decision at bar *t* may use data up to and including bar *t*'s **close**,
  and nothing later. Enforce structurally: the replay iterator MUST NOT expose future bars, and the feature
  library MUST take a right-bounded window. Do not rely on discipline; make it impossible.
- **R-8.2.b — Fills happen at the *next* bar.** A signal generated from bar *t*'s close fills at bar
  *t+1*, never at *t*'s close. Filling at the close of the bar that generated the signal is the most common
  backtesting bug in existence and it manufactures spectacular fake returns.
- **R-8.2.c — Model the spread explicitly.** Buys fill at ask, sells at bid. Never at mid, never at close.
- **R-8.2.d — Model slippage.** Minimum: `slippage_bps = 0.5·spread_bps + k·(order_size / bar_volume)`,
  with `k` calibrated against live paper fills once available (Section 16.6). Assume worse until measured.
- **R-8.2.e — Model fees.** Alpaca equity commission is $0, but SEC Section 31 fees and FINRA TAF apply on
  sells and are real. Include them. They are small and they matter at high turnover.
- **R-8.2.f — Cap participation.** An order MUST NOT exceed **1%** of that bar's volume. Above that you are
  backtesting a fill that would not have happened.
- **R-8.2.g — Model rejection and halts.** Trading halts (LULD) MUST be simulated from the data where
  available. A strategy that assumes it can always exit is not modelling its worst days.
- **R-8.2.h — Use adjusted prices for features, unadjusted for fills.** Splits and dividends otherwise
  create phantom gaps that the model will happily learn.

### 8.3 Outputs

Every backtest run MUST emit, to object storage under a content-hashed run ID:

- Full trade blotter (entry/exit timestamps, prices, sizes, fees, slippage, reason).
- Equity curve at 1-minute resolution.
- Metrics: total & annualised return, **Sharpe and deflated Sharpe**, Sortino, max drawdown, drawdown
  duration, win rate, profit factor, average win/loss, turnover, exposure time, and **the Section 2.1 cost
  drag figure**.
- Per-regime breakdown: bull/bear/sideways, high/low VIX, by month. A strategy that only works in one regime
  needs to be known as such.
- The exact config, git SHA, and data snapshot manifest hash.

**R-8.3.a** Backtest runs MUST be reproducible: same run ID → byte-identical blotter. Seed every RNG.
If you cannot reproduce a result, you cannot debug it.

---

## 9. Machine learning methodology

This section is the intellectual core. The techniques are from Marcos López de Prado's *Advances in
Financial Machine Learning*; they exist because standard ML practice **silently fails** on financial data,
and following the standard practice is the reason most retail ML trading projects produce great backtests
and lose money.

### 9.1 Why standard ML practice breaks here

| Standard assumption | Reality in markets | Consequence if ignored |
|---|---|---|
| Samples are i.i.d. | Overlapping labels share price paths; returns are autocorrelated | Random K-fold leaks the future into training. Your CV score is fiction |
| Fixed-horizon returns are a fine label | Ignores the path — a trade that hits your stop before your target is a loss, not a win | The model optimises something you will never actually trade |
| More features are better | Noise features + low signal-to-noise = memorisation | Backtest looks superb, live is random |
| One good backtest = a good strategy | You ran 500 variants and picked the best | Selection bias. The winner is the luckiest, not the best |

### 9.2 Feature engineering

Grouped, all computed by the shared feature library (R-4.4.a):

- **Price/return:** returns over 1/5/15/30/60m, overnight gap, distance from VWAP (in ATR units), distance
  from prior day's high/low/close, position within the day's range.
- **Volume:** relative volume vs 20-day same-time-of-day profile, volume acceleration, dollar volume,
  trade-count-to-volume ratio (average trade size — a crude institutional-participation proxy).
- **Volatility:** ATR%, realised vol over multiple windows, Parkinson/Garman-Klass estimators, vol-of-vol.
- **Microstructure:** spread in bps, spread volatility, quoted depth imbalance *if quote data is licensed*.
- **Time:** minutes since open, minutes to close, time-of-day bucket, day of week. Intraday seasonality is
  one of the few genuinely robust effects in this data.
- **Cross-sectional:** the symbol's rank *within today's 50* on each of the above. Relative features are
  usually more robust than absolute ones because they self-normalise across regimes.
- **Market context:** SPY/QQQ return and vol over matching windows, VIX level and change, sector ETF return,
  the symbol's beta-adjusted residual return.
- **Event flags:** earnings within ±2 days, ex-dividend, index add/drop, halt earlier today.

**Rules:**

- **R-9.2.a** Every feature MUST be computable in live trading from data available at that instant. Write the
  live path first; if it is awkward there, the feature is wrong.
- **R-9.2.b** Features MUST be normalised **cross-sectionally within the day** (rank or z-score across the 50),
  not globally over history. Global normalisation leaks future distribution information into the past.
- **R-9.2.c** Start with ≤ **40** features. Adding features is cheap and almost always harmful at this
  sample size. Every addition MUST be justified by out-of-sample improvement, not in-sample.
- **R-9.2.d** Compute **feature importance via permutation on out-of-sample data**, not LightGBM's built-in
  split-count importance, which is biased toward high-cardinality features.

### 9.3 Labelling — the triple-barrier method

Do not label with fixed-horizon returns. Label with what would actually have happened to a real trade.

For each candidate entry, set three barriers and label by whichever is touched first:

| Barrier | Default | Label |
|---|---|---|
| Upper (profit target) | `entry + 2.0 × ATR(14)` | `+1` win |
| Lower (stop loss) | `entry − 1.0 × ATR(14)` | `−1` loss |
| Vertical (time) | end of session (15:55 ET) | `sign(P&L)`, or `0` if inside a dead band |

- **R-9.3.a** Barriers MUST be volatility-scaled (ATR multiples), never fixed percentages. A 1% move means
  something completely different in a 0.8%-ATR stock than in an 8%-ATR one.
- **R-9.3.b** The 2:1 reward:risk default means a ~40% hit rate is break-even before costs. The model's job
  is not "be right often" — it is "be right often enough, given the payoff." Report hit rate and profit
  factor together; either alone is misleading.
- **R-9.3.c** Barrier-touch evaluation MUST use the **path** through intraday bars (high/low), not closes.
  Using closes misses stops that were hit and then recovered — a systematic and very flattering error.
- **R-9.3.d** Apply **sample-uniqueness weights**: overlapping labels are not independent observations and
  must not be counted as such.

### 9.4 Meta-labelling

Two models, as in 7.3. The primary decides *direction*; the meta-model decides *whether to act and how big*.

The reason: a primary model tuned for high recall catches most real opportunities but also much noise. Rather
than compromise it toward precision, train a second model on the primary's own signals — features plus the
primary's score — with the label "did this signal actually win?". The meta-model's output becomes the
position sizer.

- **R-9.4.a** The meta-model MUST be trained on out-of-sample primary predictions (from walk-forward folds).
  Training it on in-sample primary output teaches it to trust a model that does not exist in production.
- **R-9.4.b** The meta-model MUST only reduce risk — veto, or scale size in `[0, 1]`. It MUST NOT be able to
  increase size beyond the risk governor's allocation or reverse direction.

### 9.5 Data hygiene — the four biases that will fake your results

- **R-9.5.a — Survivorship.** The training universe MUST be reconstructed *as of* each historical date,
  including names later delisted, acquired, or bankrupt (hence R-5.a). Training on today's symbol list is
  training on a list of survivors.
- **R-9.5.b — Look-ahead.** Fundamentals, index membership, sector classification, and corporate actions MUST
  be point-in-time. If you cannot establish when a fact became public, do not use it as a feature.
- **R-9.5.c — Data snooping.** Every experiment MUST be logged to the model registry, including failures.
  The **deflated Sharpe ratio** must be computed using the *actual* number of trials run. If you test 200
  configurations, the best one's Sharpe is inflated by construction and you must discount it accordingly.
- **R-9.5.d — The final holdout is sacred.** Reserve the most recent **6 months**. It may be touched **once**,
  at promotion. If you look at it, tune, and look again, it is no longer out-of-sample and you have lost your
  only honest estimate of live performance. Enforce this with a separate credential or bucket path if you
  have to.

### 9.6 Validation and baselines

**Walk-forward with purging and embargo — never random K-fold:**

```
 |--------- train ---------|purge|-- test --|embargo|
 |------------- train -------------|purge|-- test --|embargo|
 |------------------ train ------------------|purge|-- test --|
   expanding window · purge = label horizon (1 session) · embargo = 1 session
```

Purging removes training samples whose labels overlap the test period. The embargo drops samples immediately
after the test window, where serial correlation would still leak.

**Mandatory baselines.** The model MUST be compared against all of these on identical data, costs, and
periods, and the comparison MUST appear in every evaluation report:

1. **Random 10** — pick 10 at random from the Stage A 50, same entry/exit logic. *If the model cannot beat
   this, it has learned nothing.*
2. **Buy-and-hold SPY** over the same period.
3. **Always flat** — zero trades, zero costs. A remarkable number of strategies lose to this.
4. **Stage A score only** — take the top 10 by the deterministic `score_A`, no ML. *If the model cannot beat
   this, the ML layer is not earning its complexity and should be deleted.*

- **R-9.6.a** Baseline 4 is the one that matters most. Be honest about it.

### 9.7 Promotion gates 🔴

A model may not advance a stage unless it clears **every** gate. **These MUST be implemented as code that
the deployment path calls and refuses to proceed on failure** (R-2.1.b) — not a checklist someone reads.

| Gate | Threshold |
|---|---|
| Out-of-sample deflated Sharpe | ≥ 1.0 |
| OOS max drawdown | ≤ 15% of starting equity |
| Beats baselines 1, 3 and 4 on risk-adjusted return | Required |
| Profit factor, net of modelled costs | ≥ 1.25 |
| Cost drag (Section 2.1) | ≤ 40% of gross P&L |
| Performance in the worst regime bucket | Not catastrophic (DD ≤ 25%) |
| Probabilistic Sharpe ratio | ≥ 0.95 confidence Sharpe > 0 |
| Live-shadow tracking error vs backtest, 4 weeks | ≤ 20% divergence in daily P&L correlation |
| Minimum OOS trade count | ≥ 400 |

**The promotion ladder:** `candidate → shadow (predicts, never trades) → paper (trades paper money) →
live (micro size) → live (full size)`. Minimum dwell time: **4 weeks at shadow, 8 weeks at paper**.

**R-9.7.a** There is no override flag. If you find yourself wanting one, the correct action is to conclude
the model is not ready. Adding a bypass to this ladder defeats the purpose of the entire document.

### 9.8 Retraining and drift

- Retrain weekly on expanding data; promote only through the ladder above.
- Monitor **feature drift** (population stability index vs training distribution) and **prediction drift**
  (calibration of predicted vs realised win rate) daily.
- **R-9.8.a** PSI > 0.25 on any top-10 feature, or realised win rate outside the model's calibrated
  confidence band for 5 consecutive sessions, MUST auto-demote the model to shadow and notify the operator.
  Markets change; a model that was right last quarter has no entitlement to be right this one.

---

## 10. Execution and risk management

**This is the safety-critical subsystem.** It has the highest test-coverage bar in the repo (Section 16).
The model decides what *might* be profitable; the risk governor decides what is *permitted*. When they
disagree, the risk governor wins, always, without exception or override.

### 10.1 The risk governor

Every order passes through `engine/risk/governor.py` before reaching the broker. It is a pure function:
`(proposed_order, account_state, authorization, session_state) → Approved | Rejected(reason)`.

**R-10.1.a** The governor MUST be pure and side-effect free, so it is exhaustively unit-testable.
**R-10.1.b** There MUST be exactly one code path from decision to broker, and it MUST pass through the
governor. No "urgent" bypass, no direct broker call elsewhere in the codebase. Enforce in CI with a lint
rule that fails if `broker.submit_order` is called outside `engine/execution/`.
**R-10.1.c** Every check MUST be recorded in `decisions.risk_checks`, pass or fail, with its inputs.

### 10.2 Pre-trade checks (all must pass)

| Check | Rule |
|---|---|
| Authorization valid | Exists, unexpired, unrevoked, mode permits this action |
| Symbol permitted | In today's Stage B set (or `allowed_symbols`) |
| Buying power | Fresh from broker (R-2.2.b), sufficient with 20% headroom |
| Position count | `< max_position_count` |
| Notional cap | Position + existing exposure `≤ max_notional` |
| Per-trade risk | Risk at stop `≤ 1%` of equity (Section 10.4) |
| Daily loss limit | Realised + unrealised loss today `< max_daily_loss` |
| Concentration | ≤ 20% of equity in one symbol; ≤ 40% in one sector |
| Data freshness | Last bar for this symbol < 90 seconds old |
| Market state | Regular session, symbol not halted |
| Time window | Entries only 09:35–15:30 ET |
| Duplicate guard | No open order or position in this symbol in this direction |
| Order sanity | Limit price within 5% of last trade; qty > 0; notional ≥ $100 |
| Rate limit | ≤ 10 orders/minute, ≤ 100 orders/day |

**R-10.2.a** Any check that cannot be evaluated (stale data, broker unreachable) MUST be treated as
**FAILED**, never as passed. Fail closed. An unknown state is a dangerous state.

### 10.3 Circuit breakers (halt the session automatically)

| Trigger | Action |
|---|---|
| Daily loss limit reached | Flatten all, halt for the day, notify `critical` |
| 3 consecutive losing trades | Halt entries for 30 minutes, notify `warn` |
| Market data feed stale > 2 min during session | Halt entries, keep exits working, notify `critical` |
| Broker API error rate > 20% over 5 min | Halt entries, notify `critical` |
| Position/order reconciliation mismatch | **Halt immediately, flatten nothing, notify `critical`** — a mismatch means the engine's model of reality is wrong, and acting on a wrong model is worse than doing nothing. Requires human resolution |
| Equity drops > 5% intraday | Flatten all, halt, notify `critical` |
| Unhandled exception in the engine loop | Cancel all open orders, halt, notify `critical` |
| Model drift breach (R-9.8.a) | Demote to shadow, halt entries, notify `warn` |

**R-10.3.a** Halts MUST be sticky: once halted, the session stays halted until the operator explicitly
resumes. Auto-resume on a recovered condition is forbidden — the condition that caused the halt may still
be developing.

### 10.4 Position sizing

Risk-based, never fixed share counts:

```
risk_per_trade   = equity × risk_pct              # default 0.5%, hard max 1.0%
stop_distance    = entry_price − stop_price       # from ATR, per Section 9.3
base_size        = risk_per_trade / stop_distance
final_size       = floor(base_size × meta_model_confidence)   # confidence ∈ [0, 1]
```

Then clamp by: notional cap, concentration limits, participation cap (≤ 1% of recent bar volume), and
buying power.

- **R-10.4.a** `risk_pct` MUST start at **0.25%** for live trading and MUST NOT be raised until at least
  **3 months** of live results exist. With a 0.5% risk and a 1% daily loss limit, a bad streak costs weeks,
  not the account — which is the entire point.
- **R-10.4.b** The system MUST NOT implement martingale, averaging down, or any size-up-after-loss logic.
  These convert a losing strategy into a catastrophically losing strategy.

### 10.5 Order lifecycle and idempotency

Duplicate orders are the most expensive class of bug in a trading system. The mechanism that prevents them:

- **R-10.5.a** Every order MUST carry a deterministic `client_order_id`, derived as
  `sha256(decision_id || symbol || side || qty)`, sent to the broker as the client order ID. If the engine
  crashes mid-submit and retries, the broker rejects the duplicate rather than opening a second position.
- **R-10.5.b** The `orders` row MUST be written to Postgres **before** the broker call, status
  `pending_submit`. Write-ahead, then act. If the process dies between the two, recovery sees the intent and
  can reconcile against the broker.
- **R-10.5.c** Order state MUST be driven by the **broker's trade-update stream**, not by polling and not by
  the engine's assumptions. The broker is the source of truth for order and position state, always.
- **R-10.5.d** Partial fills MUST be handled explicitly — bracket legs resized to the filled quantity.
- **R-10.5.e** Every state transition MUST be idempotent. The same trade-update event delivered twice MUST
  produce the same final state.

### 10.6 End-of-day flatten

- **15:45 ET** — cancel all unfilled entry orders.
- **15:50 ET** — begin closing positions with limit orders at the near touch.
- **15:55 ET** — convert anything unfilled to market orders.
- **15:58 ET** — if anything is still open, notify `critical` and page the operator.

**R-10.6.a** The EOD flatten MUST be driven by a timer independent of the strategy loop, so a hung or
crashed strategy cannot leave positions open overnight. It MUST also run if the engine restarts at 15:52.
**R-10.6.b** The flatten policy on revocation (R-6.5) is operator-chosen: `flatten_immediately` (market
orders now) or `cancel_orders_hold_positions` (stop new risk, leave existing positions to the EOD timer).
Default `flatten_immediately`.

### 10.7 Crash recovery

On boot, the engine MUST, before doing anything else:

1. Acquire the singleton lease (R-3.1.a). If it cannot, exit — do not proceed.
2. Fetch **all** open orders and positions from the broker.
3. Reconcile against Postgres. Any mismatch → **halt and notify**, do not self-heal. Automatic reconciliation
   of an unknown discrepancy risks turning a small problem into a large one.
4. Re-attach bracket protection to any unprotected position.
5. Only then resume the strategy loop.

**R-10.7.a** The engine MUST NOT assume it is starting fresh. Assuming a clean slate after a crash is how
positions get doubled.

---

## 11. Broker and market data integration — Alpaca

**Alpaca is the single venue for both simulated and real trading.** This is a deliberate and important
choice: the paper and live environments share the same API surface, the same order types, the same
authentication model, and the same data feed. Going live is a **base-URL and credential change**, not a
rewrite — so the code that survives eight weeks of paper trading is *literally the same code* that trades
real money, and nothing untested appears at the riskiest moment.

### 11.1 Environments

| | Paper | Live |
|---|---|---|
| Trading base URL | `https://paper-api.alpaca.markets` | `https://api.alpaca.markets` |
| Data base URL | `https://data.alpaca.markets` (same) | same |
| Credentials | Paper key pair | Live key pair — **separate secret store entry** |
| Env flag | `ALPACA_ENV=paper` | `ALPACA_ENV=live` |

- **R-11.1.a** `ALPACA_ENV` MUST be explicit with **no default**. A missing value MUST crash the process at
  startup. Never let the absence of configuration resolve to live trading.
- **R-11.1.b** Live credentials MUST NOT exist in any environment except the production `engine` and `api`
  machines. Not in CI, not in `.env.example`, not on the developer's laptop, not in the MCP config
  (Section 19.1).
- **R-11.1.c** The UI MUST display a prominent, persistent, colour-coded banner showing which environment is
  active. Paper = blue. Live = red.
- **R-11.1.d** Switching to live MUST require a deliberate deploy with a changed secret — never a runtime
  toggle, never a feature flag, never an admin button.

### 11.2 Market data

- **Feed:** SIP (Algo Trader Plus, $99/mo) for everything that matters — see R-2.4.b. IEX free tier for
  local development only.
- **Streaming:** WebSocket subscription to 1-minute bars + trades for the ten selected symbols. Subscribe at
  09:25 after Stage B, unsubscribe at 16:00.
- **Historical:** REST for the nightly ingest. Alpaca provides minute bars going back years on funded
  accounts, which is the training corpus.
- **R-11.2.a** The WS client MUST auto-reconnect with exponential backoff **and** MUST backfill the gap via
  REST on reconnect. A silent gap in the bar stream produces wrong features, which produce wrong trades.
- **R-11.2.b** Bar staleness MUST be tracked per symbol and surfaced to the risk governor (Section 10.2).
- **R-11.2.c** Record `feed` provenance on every bar (R-2.4.c).

### 11.3 Trading

- Bracket orders for all entries (R-7.3.d). Limit orders for entries; market orders only in the EOD flatten.
- Subscribe to the **trade updates stream** for authoritative order state (R-10.5.c).
- Respect rate limits (10,000 rpm on Algo Trader Plus); implement a token-bucket limiter in the broker client
  regardless, because the limit on the free tier is 200 rpm and dev must not diverge from prod behaviour.
- **R-11.3.a** All broker calls MUST have timeouts (5s connect, 10s read) and MUST NOT retry non-idempotent
  operations without the `client_order_id` guard (R-10.5.a).

### 11.4 Abstraction

- **R-11.4.a** All broker interaction MUST go through a `BrokerPort` protocol in `engine/broker/`. The
  simulated broker in the backtester MUST implement the same protocol. This is what makes backtest and live
  behaviour comparable, and it keeps a future broker migration tractable.

---

## 12. Funding, capital policy, and cash-out

### 12.1 Do not build money movement — this is important

The brief's step 1 is "user provides a bank account or general funding" and step 5 is "cash out." The
instinct is to build bank linking into the app. **Do not.**

Moving customer funds through your own system implicates money-transmitter licensing, and the Alpaca product
that supports programmatic bank linking and transfers on behalf of users (**Broker API**, with Plaid
processor tokens) is a partner product for businesses onboarding *their customers* — it is not what an
individual uses for their own account.

For a personal account the correct architecture is:

- The operator funds their own Alpaca account directly, through **Alpaca's own ACH flow** (free deposits and
  withdrawals, standard for US residents).
- **This app never touches the bank connection and never holds funds.** It reads balances from the Trading
  API and deep-links to Alpaca for any money movement.

**R-12.1.a** The app MUST NOT store bank credentials, Plaid tokens, or account/routing numbers.
**R-12.1.b** The "Funding" UI is a **read-only dashboard** — equity, cash, buying power, deposits/withdrawals
history from the broker — plus a deep link to Alpaca's transfer page. Requirements 1 and 5 are satisfied by
*surfacing* the state, not by intermediating the money.
**R-12.1.c** Cash-out: a "Withdraw" button computes and displays what is safely withdrawable (settled cash,
less any open exposure and a reserve buffer), warns if a withdrawal would breach the strategy's minimum
working capital, then deep-links out. The value this app adds is the *calculation and the warning*, not the
transfer.

### 12.2 Capital policy — core and satellite 🔴

**R-12.2.a** The capital allocated to this bot MUST be a **satellite sleeve**, not the operator's portfolio.
Given the base rates in Section 2.1, the starting allocation SHOULD be an amount whose total loss would be
disappointing rather than damaging — treat it as the cost of an education with a chance of a return.

**R-12.2.b** The remaining "core" capital is out of this system's scope and MUST NOT be reachable by the
engine. Practical enforcement: **keep the core in a different account at a different institution.** The
engine physically cannot trade what it has no credentials for, and that is a much stronger guarantee than
any limit in code.

**R-12.2.c** The UI MUST always show the satellite sleeve's performance **next to** a simple buy-and-hold
benchmark over the same period, with the same starting capital. The honest comparison must be unavoidable,
not buried in an analytics tab.

### 12.3 Withdrawal discipline

- **R-12.3.a** The system SHOULD implement a configurable profit-sweep: when the sleeve exceeds its high
  water mark by more than X%, notify the operator to consider withdrawing the excess. Systematically taking
  profits off the table is one of the few retail behaviours the literature supports.

---

## 13. Notifications

**No A2P campaign, no carrier registration, no multi-day lead time.** This is a one-operator system sending
messages to one person, so it does not need the machinery built for businesses messaging strangers.

### 13.1 Why not a Twilio 10DLC campaign

Worth recording, because the obvious path is a trap:

- **Twilio trial accounts cannot register for A2P 10DLC at all** — that requires a paid account.
- Campaign review currently runs **10–15 days**.
- The entire regime exists to police businesses messaging consumers who did not ask for it. You are messaging
  yourself.

So the system is built channel-agnostic, with the free, zero-registration channels as the primary path.

### 13.2 Channels

| Priority | Channel | Cost | Registration | Role |
|---|---|---|---|---|
| **1** | **Telegram Bot API** | Free, unlimited | None — create a bot in 60 seconds | **Primary.** All alerts, and all interactive approve/halt actions |
| **2** | **Resend email** | Free tier: 3,000/mo, **100/day**, one verified domain | Domain DNS records | Digests, daily/weekly reports, redundant copy of every `critical` |
| **3** | **Twilio SMS** *(optional)* | Free trial credit | **Verified caller ID only — no campaign** | Optional redundant path for `critical` only |

**Why Telegram is primary and not a fallback:** it is free and unmetered, delivers in under a second, and —
unlike SMS — supports **inline buttons**. An approval prompt becomes two tappable buttons rather than a
six-character code typed back correctly under time pressure. For the approval flows in Section 6 that is a
material safety improvement, not a convenience.

- **R-13.2.a** Notifications MUST go through a `NotificationPort` protocol with one adapter per channel. No
  channel may be referenced directly outside its adapter. Adding, removing, or swapping a channel is then a
  config change, which matters because this is the part of the stack most likely to change.
- **R-13.2.b** The system MUST function fully with **only** Telegram and email configured. Twilio MUST be
  optional and its absence MUST NOT degrade any safety property.

### 13.3 Twilio, if used

Only if the operator wants true SMS as a redundant critical path.

- **R-13.3.a** Use a **trial account with the operator's own number added as a Verified Caller ID.** Trial
  accounts can send to verified numbers without any campaign. Messages carry a trial prefix; that is fine.
- **R-13.3.b** Do **not** register an A2P 10DLC campaign. If trial credit is ever exhausted, the decision is
  "upgrade to a paid account" or "drop SMS" — it is never a blocker, because of R-13.2.b.
- **R-13.3.c** Twilio MUST carry **`critical` severity only**. This keeps volume at a handful of messages a
  month and inside any free allowance.

### 13.4 Respecting the free tiers

The email free tier caps at **100/day**, and 3,000/month averages to exactly that — the daily limit is a real
ceiling, not slack.

- **R-13.4.a** Email MUST NOT be sent per-trade. Trades are accumulated and sent as **one end-of-day digest**.
  A ten-name day with several round trips each would otherwise burn a third of the daily allowance on
  information nobody reads in real time.
- **R-13.4.b** The notifier MUST track its own daily send count per channel and MUST log and alert when it
  reaches **80%** of a known limit.
- **R-13.4.c** If an email quota is exhausted, `critical` events MUST still go out via Telegram (and SMS if
  configured). **A quota MUST NEVER be able to suppress a critical alert** — reserve headroom by design:
  `info` email is budgeted at ≤ 20/day, leaving 80 in reserve.

### 13.5 Event catalogue

| Event | Severity | Telegram | Email | SMS (if on) |
|---|---|---|---|---|
| Morning plan ready (the 10) | info | ✓ with Approve/Reject buttons | ✓ full reasoning | — |
| Approval requested (manual mode) | info | ✓ with buttons | — | — |
| Trade entered / exited | info | batched, 15-min | in EOD digest (R-13.4.a) | — |
| Daily loss limit hit | critical | ✓ | ✓ | ✓ |
| Circuit breaker tripped | critical | ✓ | ✓ | ✓ |
| Reconciliation mismatch | critical | ✓ | ✓ | ✓ |
| Engine down during market hours | critical | ✓ | ✓ | ✓ |
| Positions open after 15:58 | critical | ✓ | ✓ | ✓ |
| Model drift / auto-demotion | warn | ✓ | ✓ | — |
| Daily summary + trade digest | info | ✓ short | ✓ full | — |
| Weekly performance report | info | — | ✓ | — |

### 13.6 Inbound: approvals and the kill switch

The Telegram bot is the interactive channel. Commands: `/halt`, `/status`, `/positions`, `/flatten`,
plus inline callback buttons on approval prompts.

**Security — this endpoint can move money, so treat it accordingly:**

- **R-13.6.a** The Telegram webhook MUST be registered with a **secret token**, and every inbound request MUST
  be validated against the `X-Telegram-Bot-Api-Secret-Token` header. Mismatch → 403, no processing.
- **R-13.6.b** The handler MUST enforce a **single allowlisted `chat_id`**. Anyone who learns your bot's
  username can message it; only one chat may command it. Every other chat is silently ignored and logged.
- **R-13.6.c** Approval callbacks MUST be bound to a specific `decision_id`, single-use, and expire in **10
  minutes** (as R-6.7). A stale button tap MUST do nothing.
- **R-13.6.d** If Twilio SMS is enabled, its webhook MUST validate `X-Twilio-Signature` (R-6.8) and enforce a
  single allowlisted sender number.
- **R-13.6.e** Inbound channels MUST NOT be able to grant authorization or raise a limit (R-6.9). They may
  approve a specific pending action, or halt. **Halting is always allowed, from any allowlisted channel,
  with no code and no confirmation** (R-6.10).

### 13.7 General rules

- **R-13.7.a** Every notification MUST carry a `dedupe_key`; the notifier MUST NOT send twice for the same
  key. Delivery is at-least-once; the key makes it effectively once.
- **R-13.7.b** Non-critical alerts MUST be batched — at most one every 15 minutes, aggregating events.
- **R-13.7.c** `critical` MUST bypass batching, quiet hours, and every quota consideration.
- **R-13.7.d** Message bodies MUST NOT contain account numbers or full balances. Phones get lost and none of
  these channels is a confidential medium.
- **R-13.7.e** A send failure MUST be retried (3×, exponential backoff), then logged `failed` and escalated to
  the next channel. A critical alert that silently failed to send is a critical alert that did not happen.
- **R-13.7.f** Quiet hours (default 21:00–07:00 ET) suppress `info` only.
- **R-13.7.g** The weekly kill-switch drill (R-16.5.a) MUST exercise the **real** inbound path end to end,
  not a mocked one. A kill switch tested only against a mock is untested.

## 14. Frontend and API surface

### 14.1 Screens

| Route | Purpose | Key elements |
|---|---|---|
| `/` **Dashboard** | At-a-glance state | Env banner (paper/live), equity + today's P&L, open positions, engine health, authorization status + countdown, **HALT button** |
| `/plan` **Morning plan** | The day's pipeline output | Stage A 50 → Stage B 10, each with score, top contributing features, and plain-English reasoning. Approve / reject / edit the plan |
| `/positions` | Live positions & orders | Real-time via SSE, per-position P&L, manual close, bracket levels |
| `/journal` | Trade history | Every trade with entry/exit chart, the decision's feature vector, model version, and outcome vs expectation |
| `/performance` | Analytics | Equity curve vs buy-and-hold (R-12.2.c), drawdown, win rate, profit factor, **cost drag**, per-regime breakdown |
| `/models` | Model registry | Versions, promotion state, gate results, drift monitors, promote/demote (promotion gated by Section 9.7) |
| `/backtests` | Research results | Run list, metrics, blotters, comparison against baselines |
| `/funding` | Capital | Read-only balances, deposit/withdrawal history, safe-to-withdraw calculator, deep links to Alpaca (R-12.1.b) |
| `/authorize` | Grant/revoke | Mode, caps, expiry, flatten policy. TOTP re-challenge required |
| `/settings` | Config | Notification prefs, risk defaults, quiet hours, scanner thresholds |
| `/audit` | Audit log | Searchable, append-only record of everything |

### 14.2 Frontend rules

- **R-14.2.a** The UI MUST NOT compute P&L, risk, or position state. It renders what the backend reports.
  Two implementations of the same calculation will disagree, and the operator will not know which to believe.
- **R-14.2.b** Live updates via **SSE** (`GET /v1/stream`), not polling. Reconnect with backoff; show a stale-
  data indicator when disconnected. A dashboard that silently shows stale numbers during a market event is
  actively dangerous.
- **R-14.2.c** All money formatted to 2 decimals with explicit currency; all times shown in `America/New_York`
  with the timezone label visible. Ambiguity about whether a timestamp is UTC or ET causes real mistakes.
- **R-14.2.d** Destructive actions (halt, flatten, revoke, promote to live) require a typed confirmation.
- **R-14.2.e** The env banner (R-11.1.c) MUST be rendered server-side from the backend's reported
  environment, so a stale client build cannot show the wrong one.

### 14.3 API surface (FastAPI, all under `/v1`, all authenticated)

```
GET    /health                         liveness + dependency status (public)
GET    /account                        balances, buying power (from broker)
GET    /stream                         SSE: positions, orders, P&L, engine status

GET    /plan/{date}                    stage A + B output with features & reasoning
POST   /plan/{date}/approve            approve today's plan            [TOTP]
POST   /plan/{date}/reject

GET    /authorizations                 current + history
POST   /authorizations                 grant                           [TOTP]
DELETE /authorizations/{id}            revoke                          [no TOTP — kill switch]

GET    /positions                      GET /orders   GET /trades
POST   /positions/{symbol}/close       manual close                    [confirm]
POST   /engine/halt                    immediate halt                  [no TOTP]
POST   /engine/resume                  resume after halt               [TOTP]
POST   /engine/flatten                 close everything now            [confirm]

GET    /performance                    metrics over a period
GET    /models   GET /models/{version}
POST   /models/{version}/promote       runs Section 9.7 gates; 409 on failure   [TOTP]
POST   /models/{version}/demote

GET    /backtests   GET /backtests/{id}   POST /backtests    (enqueue)
GET    /funding/summary                balances + safe-to-withdraw calc
GET    /audit                          paginated, filterable

POST   /webhooks/telegram              inbound commands + approval callbacks  [secret token — R-13.6.a]
POST   /webhooks/twilio                inbound SMS, optional   [X-Twilio-Signature — R-6.8]
```

- **R-14.3.a** Revoke and halt MUST NOT require TOTP. Every second of friction on a kill switch is a second
  of unwanted exposure, and the downside of an accidental halt is negligible.
- **R-14.3.b** All mutating endpoints MUST accept an `Idempotency-Key` header and MUST be safe to retry.
- **R-14.3.c** `/health` MUST report dependency status (broker, data feed, DB, Redis) individually, not a
  single boolean. "Something is wrong" is not an actionable alert.

---

## 15. Security and observability

### 15.1 Security

- **R-15.1.a** Secrets live in Fly.io secrets and Vercel env vars. **Never** in the repo, never in
  `.env.example` with real values. Add a `gitleaks` pre-commit hook and a CI secret scan.
- **R-15.1.b** Single-user allowlist: exactly one email address may authenticate. Everything else is a 403.
- **R-15.1.c** TOTP MFA is mandatory, not optional.
- **R-15.1.d** The `api` service MUST only accept requests from the Vercel deployment origin and the
  notification providers'
  webhook IP ranges. Everything else rejected at the edge.
- **R-15.1.e** Live trading credentials MUST be rotated if they ever appear in a log, a terminal, or a
  screenshot. Assume compromise; rotation is cheap.
- **R-15.1.f** Structured logs MUST redact keys, tokens, and full account numbers via a logging filter, not
  by remembering to.
- **R-15.1.g** Dependabot on, CI blocks on critical CVEs.

### 15.2 Metrics (OpenTelemetry → Grafana)

- Engine loop latency (p50/p95/p99), bar-to-decision latency, decision-to-order-ack latency.
- Orders submitted / filled / rejected / canceled per minute.
- **Slippage: realised fill price vs the price at decision time.** Track this from day one — it is the
  number that decides whether the backtest means anything (Section 16.6).
- WS reconnect count, bar staleness per symbol, broker error rate.
- Risk governor rejections by rule.
- Model: prediction distribution, calibration error, feature PSI.

### 15.3 Alerts

`critical` → SMS + email + Sentry. Chief among them: engine not running 09:25–16:00 on a trading day;
reconciliation mismatch; positions open after 15:58; equity change > 5% in an hour.

### 15.4 Runbooks (`docs/runbooks/`)

Write these **before** they are needed, one page each: engine crash mid-session; reconciliation mismatch;
broker API outage; data feed outage; duplicate orders detected; positions stuck open past close; suspected
credential compromise; "I need to stop everything right now."

**R-15.4.a** Each runbook MUST be written to be followed by a stressed person on a phone. Numbered steps,
no prose, exact commands.

---

## 16. Testing

### 16.1 Coverage bar

| Component | Requirement |
|---|---|
| `engine/risk/` | **100% branch coverage**, no exceptions |
| `engine/execution/`, `engine/broker/` | ≥ 90% |
| `research/backtest/` | ≥ 90% + golden tests |
| `research/features/` | ≥ 90% + live/backtest parity tests |
| Everything else | ≥ 70% |

### 16.2 Unit tests

Property-based tests (`hypothesis`) for the risk governor: for any account state, authorization, and
proposed order, the governor must never approve something exceeding the caps. Generate adversarial inputs —
zero equity, negative cash, expired authorizations, NaN prices, zero-volume bars.

### 16.3 Backtester golden tests 🔴

The backtester MUST reproduce known-correct results on hand-computed fixtures:

- A single flat-price bar series → zero P&L minus fees.
- A known ramp with a known entry/exit → hand-computed P&L to the cent.
- **A look-ahead canary:** a strategy that cheats (peeks at bar *t+1*) MUST be detectable — a test that
  asserts the replay iterator raises when future data is accessed.
- Fill-timing: a signal at bar *t* MUST fill at bar *t+1* (R-8.2.b). Assert explicitly.
- Fees and slippage applied and matching hand calculation.

**R-16.3.a** These tests are the foundation of every number this system produces. Write them first.

### 16.4 Feature parity tests 🔴

**R-16.4.a** For a recorded session, features computed by the **live path** (streaming, incremental) MUST
equal features computed by the **backtest path** (batch, historical) to within 1e-9. Run this on every CI
build. This test catches training/serving skew (R-4.4.a), which is otherwise invisible until it has cost
money.

### 16.5 Chaos and drill tests

Simulate, against paper: broker returns 500s; WS disconnects mid-session; partial fill then rejection on the
remainder; symbol halted while in a position; engine killed with positions open (verify Section 10.7 recovery);
clock skew; duplicate trade-update events; database unreachable mid-order.

**R-16.5.a** The **kill switch drill** MUST run weekly against paper, automated: send `STOP`, assert
authorizations revoked and positions flattened within 10 seconds, and alert if not (R-6.12).

### 16.6 Calibrating the simulation against reality 🔴

**R-16.6.a** During paper trading, continuously compare **modelled** slippage (R-8.2.d) to **realised**
slippage. If realised exceeds modelled by more than 50%, the backtester is optimistic and every promotion
gate result computed with it is invalid. Recalibrate `k` and re-run the gates.

This feedback loop is what makes Alpaca paper trading a genuine substitute for the simulator the brief
originally proposed — and it is a large part of why the Investopedia route was rejected (Section 2.3): you
cannot calibrate against a venue whose fill model is undocumented.

---

## 17. Deployment and scheduling

### 17.1 Fly.io process groups

```toml
# infra/fly.toml  (abbreviated)
[processes]
  api      = "uvicorn services.api.main:app --host 0.0.0.0 --port 8080"
  engine   = "python -m services.engine"
  worker   = "python -m services.worker.scheduler"
  notifier = "python -m services.notifier"

[[vm]]  # engine: never scale beyond 1 (R-3.1.a)
  processes = ["engine"]
  memory    = "2gb"
  cpus      = 2
```

**R-17.1.a** `engine` MUST be pinned to `min_machines_running = 1`, `max = 1`. Add a CI check that fails if
the engine count is ever configured above 1.
**R-17.1.b** `api` MUST NOT auto-stop. A suspended control plane means an unreachable kill switch.

### 17.2 Schedule (all America/New_York, trading days only)

| Time | Job | Owner |
|---|---|---|
| 04:30 | Refresh symbols, calendar, corporate actions | worker |
| 08:15 | **Stage A scan** → 50 candidates | worker |
| 08:45 | Engine boot, health checks, reconciliation | engine |
| 09:20 | **Stage B rank** → 10 names | worker |
| 09:25 | Morning plan notification; subscribe to market data | notifier/engine |
| 09:30–15:55 | **Stage C trading loop** | engine |
| 15:45/15:50/15:55/15:58 | EOD flatten ladder (Section 10.6) | engine |
| 16:15 | Reconcile, snapshot positions & account, daily report | worker |
| 17:00 | Bar ingest → Postgres + Parquet, parity check | worker |
| 18:00 | Drift monitors; weekly (Sat) retrain | worker |

**R-17.2.a** The schedule MUST be driven by the **broker's market calendar**, not a cron expression with
hardcoded dates. Holidays and early closes (13:00 ET) must be respected automatically; shift the EOD ladder
accordingly.
**R-17.2.b** A missed job MUST alert. Silence is not success.

### 17.3 CI/CD

PR: lint, typecheck, unit, integration, feature-parity, backtest goldens, generated-client freshness.
Merge to `main`: deploy `api`/`worker`/`notifier`.

**R-17.3.a** The `engine` MUST NOT be deployed during market hours. CI MUST refuse. A rolling restart at
11:30 with open positions is an incident.
**R-17.3.b** Database migrations MUST be backward-compatible for one release (expand/contract), so a rollback
does not corrupt state.

---

## 18. Compliance, legal, and tax

Not legal or tax advice. Confirm with a professional before Phase 8.

- **R-18.a — Personal use only.** This system manages the operator's own money. **Accepting anyone else's
  capital — including friends and family, including informally — likely makes this a regulated investment
  advisory business** requiring registration, compliance infrastructure, and disclosures. If that ever
  becomes the goal, stop and get counsel; the architecture changes substantially.
- **R-18.b — Wash sales.** High-turnover trading in the same names generates wash sales that defer losses.
  The system SHOULD flag likely wash sales in the journal so there are no April surprises.
- **R-18.c — Tax character.** Day-trading gains are short-term capital gains, taxed as ordinary income.
  Model after-tax returns in the performance view; pre-tax figures overstate what the operator keeps.
- **R-18.d — Trader tax status / §475(f).** If volume is high, mark-to-market election may be advantageous
  (and eliminates wash-sale tracking). It has a strict filing deadline and is difficult to revoke. Discuss
  with a CPA; do not act on this document.
- **R-18.e — Records.** The broker issues the 1099-B, but the `audit_log`, `decisions`, and `fills` tables
  are the operator's own record. Retain ≥ 7 years and back up outside the app.
- **R-18.f — Market conduct.** The system MUST NOT implement spoofing, layering, marking the close, or wash
  trading. This is not theoretical: an aggressive order-cancellation loop can incidentally resemble spoofing.
  Keep the order-to-fill ratio sane and reviewable.
- **R-18.g — Data licensing.** Market data is licensed. Redistributing SIP data outside personal use breaches
  the agreement. Keep it inside the app.
- **R-18.h — PDT.** See Section 2.2. The old $25k rule is retired; do not reintroduce it in code, and do not
  treat its absence as an increase in safety.

---

## 19. Claude tooling — MCP servers and plugins

The operator asked that Claude-side tooling be used for market data work. Three things are available and
each has a genuinely different role. **None of them is in the production hot path** — that distinction is
the most important thing in this section.

### 19.1 Alpaca official MCP server — proof of concept and research ⭐

[`alpacahq/alpaca-mcp-server`](https://github.com/alpacahq/alpaca-mcp-server) — Alpaca's **official** MCP
server, rewritten for v2 on FastMCP + OpenAPI (v2.3.1, September 2026), exposing **65 tools** across the
Trading and Market Data APIs. Works with Claude Code, Claude Desktop, Cursor, and VS Code with no init step.

This is the fastest route from zero to a working proof of concept, and it should be used heavily in
Phases 0–4. It collapses the usual "write a client, discover the response shape is different, rewrite the
client" loop into a conversation.

**Use it for — this is a first-class part of the build, not a toy:**

| Phase | What the MCP is for |
|---|---|
| **0 — POC** | Prove the whole idea end to end before committing to architecture: pull quotes, place a paper bracket order, watch it fill, inspect the position. One session, no code |
| **1 — Data** | Validate the shape and quality of Alpaca's bars before writing the ingest pipeline. Spot-check corporate actions and halts. Confirm what SIP returns that IEX does not (R-2.4.b) |
| **3 — Scanner** | Sanity-check Stage A output by hand. "Show me today's volume and spread for these 50" is a one-line question and a strong correctness check on the scanner |
| **4 — Modelling** | Prototype feature ideas conversationally before implementing them. Investigate what the model got wrong on a specific symbol and day. Interrogate outliers in the training set |
| **5–8 — Ops** | Inspect paper positions and orders while debugging. Answer "what did this symbol actually do at 10:15" without writing a script |

**On "model training" specifically — one boundary that matters.** Use the MCP to *design and validate* the
training data; do not use it to *move* the training data. The corpus is roughly 786M bars/year, and tool
calls are LLM-mediated, rate-limited, non-deterministic, and pass through a context window. Bulk historical
ingest MUST use the Alpaca REST API from `worker` (Section 11.2, Phase 1).

This is not a compromise on data quality: **it is the same Alpaca data over both paths**, so what you
validate interactively through the MCP is exactly what the pipeline ingests. That consistency is precisely
why the MCP is trustworthy for this job.

**Never in the order path.** The engine MUST call Alpaca directly through `BrokerPort` (R-11.4.a). The
reasons are not stylistic:

- Engine correctness depends on deterministic, idempotent, latency-bounded calls with `client_order_id`
  guards (R-10.5.a). An LLM-mediated tool call satisfies none of those properties.
- Every order must pass the risk governor (R-10.1.b). An MCP call bypasses it entirely.
- Non-determinism in an order path is unacceptable at any latency.

**Configuration rules:**

- **R-19.1.a** The MCP server MUST be configured with `ALPACA_PAPER_TRADE=true` and **paper keys only**.
  Live keys MUST NOT be placed in any MCP configuration, ever (R-11.1.b). A conversational interface with
  live order-placement authority is exactly what Section 6 exists to prevent.
- **R-19.1.b** Config belongs in `.mcp.json` with env-var references, never literal keys; secrets gitignored.
- **R-19.1.c** Any finding from an MCP session that informs a design decision MUST be written down — in an
  ADR, a docstring, or a test. Conversations are not a durable artifact, and "we checked that once in chat"
  is not a record.

Suggested project config:

```jsonc
// .mcp.json  — paper credentials only
{
  "mcpServers": {
    "alpaca": {
      "command": "uvx",
      "args": ["alpaca-mcp-server"],
      "env": {
        "ALPACA_API_KEY":    "${ALPACA_PAPER_KEY}",
        "ALPACA_SECRET_KEY": "${ALPACA_PAPER_SECRET}",
        "ALPACA_PAPER_TRADE": "true"
      }
    }
  }
}
```

### 19.2 BlackRock Advisor Center — portfolio oversight for the *core*, not the bot

Available as a Claude connector (`ac360-mcp.blackrock.com`) and as the
`blackrock-advisor-center-plugin`, with tools including `analyze_portfolio`, `analyze_risk`,
`analyze_scenarios`, `analyze_characteristics`, `analyze_fund_health`, `analyze_opportunities`, and
`analyze_esg`, plus skills for portfolio review, guided benchmark selection, guided portfolio building, and
wealth projections.

**Be clear about what this is.** It is professional-grade portfolio *construction and analysis* tooling
oriented to funds, ETFs, and model portfolios over long horizons. It has **no intraday data, no minute bars,
and no order routing.** It cannot feed Stage A, B, or C, and nothing in `services/` should call it.

**Where it earns its place — the core/satellite structure of Section 12.2:**

| Use | Tool / skill | Cadence |
|---|---|---|
| Stress-test the **whole** portfolio (core + bot sleeve) against historical scenarios — 2008, 2020, rate shocks | `analyze_scenarios`, `analyze_risk` | Monthly, and after any large sleeve change |
| Choose a defensible benchmark for Section 9.6 baseline 2 — is SPY right, or is a blended benchmark more honest? | `guided-benchmark-selection` | Once, revisit annually |
| Review concentration and downside exposure across everything the operator owns | `portfolio-review` | Quarterly |
| Long-horizon wealth projection: what the core is expected to do, so the sleeve's contribution is seen in proportion | `wealth-projections` | Annually |
| Fund health on core ETF/mutual-fund holdings | `analyze_fund_health` | Annually |

This is genuinely useful, because the honest question about a day-trading bot is never "did the sleeve make
money" but "did the *portfolio* do better than it would have without it." Advisor Center answers the second
question; this app only answers the first.

**Caveats to hold in mind:**

- **R-19.2.a** It requires an **Advisor Center account**, which is oriented to financial professionals. The
  operator should confirm eligibility before planning around it — this is tracked as open item **O-7**
  (Section 21). The system MUST NOT have a hard dependency on it.
- **R-19.2.b** The connector requires accepting terms (`acknowledge_terms`) before use.
- **R-19.2.c** Its analysis reflects a fund provider's perspective and surfaces BlackRock products through
  features like "Funds to Explore." Read recommendations with that lens — the *risk and scenario analytics*
  are the valuable, largely product-neutral part.
- **R-19.2.d** Use it in the operator's Claude conversations. Do **not** build a backend integration; there
  is no supported server-to-server contract here for a personal app, and adding one would create a dependency
  on a product the operator may lose access to.

### 19.3 Other available tooling

| Tool | Verdict |
|---|---|
| **Alpha Vantage MCP** (in the connector directory) | Useful for fundamentals, earnings, SEC filings, and news during research. **Free tier is 25 calls/day** — effectively unusable for real work — and real-time US data needs a premium plan. Alpaca SIP remains the source of truth for prices |
| **`data` plugin** (knowledge-work marketplace) | Genuinely useful for ad-hoc SQL and visualisation against the Postgres instance while building `/performance` |
| **Bigdata.com** connector/plugin | Sentiment, premium news, earnings-call analysis. Consider only if news-based features prove valuable in Phase 4 |
| **LSEG**, **Daloopa**, **FactSet**, **Morningstar Credit** | Institutional-grade, priced accordingly. Out of scope for a personal project |

**R-19.3.a** No MCP server or connector may be a runtime dependency of `services/`. They are for humans and
for Claude sessions. If a data source becomes necessary to the system, integrate its REST API directly, with
tests, timeouts, and error handling.

---

## 20. Build plan

Each phase ends at a 🔴 gate. **Do not start the next phase until the gate passes.** Resist the urge to
build the exciting parts early; the ordering here is deliberate, and its central principle is that
*nothing may depend on numbers you cannot yet trust.*

### Phase 0 — Foundations (week 1)
Repo scaffolding, Docker, CI, Supabase project + Alembic migrations, Fly.io app, Next.js skeleton, auth with
TOTP, health endpoints, telemetry, secret management. Create the Telegram bot and verify the allowlisted
chat ID. Open an Alpaca account, generate paper keys, configure the Alpaca MCP (19.1).

**Then do the proof of concept through the MCP before writing engine code**: pull a quote, place a paper
bracket order, watch it fill, inspect the position, close it. One conversation. It proves the account, keys,
permissions, and order semantics all work, and it surfaces Alpaca's actual response shapes before any of them
are baked into a client. Record what you learn per R-19.1.c.

🔴 **Gate 0:** CI green; `/health` reachable from the deployed frontend; operator can log in with TOTP;
`.mcp.json` works against paper; a round-trip paper trade has been placed and closed through the MCP.

### Phase 1 — Data spine (weeks 2–3)
Alpaca market data client (REST + WS), symbol/calendar sync, nightly bar ingest to Postgres + Parquet with
parity check, DuckDB research access, corporate-action handling, **point-in-time symbol history (R-9.5.a)**.
🔴 **Gate 1:** ≥ 2 years of SIP minute bars ingested for the liquid universe; parity check passes; a DuckDB
query over the corpus returns correct results for a hand-verified symbol/day.

### Phase 2 — Backtester (weeks 4–5)
Event-driven replay, simulated broker implementing `BrokerPort`, spread/slippage/fee models, metrics, trade
blotter, reproducibility.
🔴 **Gate 2:** All golden tests pass (16.3), including the look-ahead canary and the fill-timing assertion.
A trivial strategy produces hand-verifiable P&L to the cent.

### Phase 3 — Stage A scanner (week 6)
Deterministic filters, composite score, config versioning, historical replay of the scanner.
🔴 **Gate 3:** Scanner runs over 2 years of history producing a stable 50/day; results reproducible; the
funnel is inspectable — you can see what was rejected and why.

### Phase 4 — ML (weeks 7–11) — *the long one; do not rush it*
Feature library (shared, R-4.4.a), triple-barrier labelling, purged walk-forward CV, LightGBM Stage B ranker,
calibration, meta-labelling, promotion gates **as code**, MLflow registry, all four baselines.
🔴 **Gate 4:** A trained model clears Section 9.7 gates on out-of-sample data **and beats baseline 4**
(Stage A score alone). *If it does not, do not proceed — iterate on features and labels, or conclude the
edge is not there.* Section 1.1 means that conclusion is a legitimate outcome, and it is far cheaper to
reach it here than in Phase 8.

### Phase 5 — Execution engine on paper (weeks 12–14)
Engine process, singleton lease, WS consumption, Stage C loop, **risk governor with 100% branch coverage**,
bracket orders, idempotency, trade-update stream, crash recovery, EOD flatten.
🔴 **Gate 5:** 10 consecutive paper sessions with zero reconciliation mismatches, zero duplicate orders, zero
positions open past 15:58. Chaos suite passes. Kill-switch drill passes.

### Phase 6 — Notifications and authorization (week 15)
`NotificationPort` with Telegram + Resend adapters (Twilio optional), event catalogue, dedupe/throttle/quota
tracking, inbound webhook with secret-token and chat-ID allowlist validation, the authorization object, kill
switch, approval flows with inline buttons.
🔴 **Gate 6:** `STOP` from a phone halts and flattens paper trading in under 10 seconds, verified three
times. A forged webhook request — wrong secret token, or a non-allowlisted chat ID — is rejected.

### Phase 7 — Frontend and shadow mode (weeks 16–18)
All screens, SSE, charts, journal, performance analytics with cost drag and the buy-and-hold comparison.
Run the full system on paper, daily, unattended.
🔴 **Gate 7:** **4 consecutive weeks** of unattended paper trading. Realised slippage within 50% of modelled
(R-16.6.a). Paper P&L tracks backtest expectations within tolerance. Operator has used the UI daily and
trusts what it says.

### Phase 8 — Live, micro-capital (week 19+)
Live credentials on production only. `risk_pct = 0.25%`. Smallest meaningful size. Daily review.
🔴 **Gate 8 — the operator's decision, not the system's:** every prior gate passed; 8+ weeks of paper results
reviewed; Section 18 items confirmed with a professional; capital allocated per R-12.2.a is an amount whose
total loss is acceptable.

**Scale up only after 3 months of live results** (R-10.4.a), and only if live tracks paper.

---

## 21. Open decisions for the operator

Do not guess at these — ask, and record the answers here.

| # | Question | Why it matters |
|---|---|---|
| **O-1** | Starting capital for the satellite sleeve? | Drives position sizing, whether the $99/mo data cost is rational, and minimum viable trade size |
| **O-2** | Long-only, or long and short? | Shorting adds borrow costs, locate requirements, and unbounded loss risk. **Recommendation: long-only through Phase 8** |
| **O-3** | Options in scope? | The brief says "day trade stock options," which is ambiguous. **This spec assumes equities only.** Options add enormous complexity — Greeks, assignment, OPRA data, spreads. Recommend deferring to v2. **Confirm the reading** |
| **O-4** | Acceptable max drawdown before shutting down entirely? | This should be decided calmly now, not during a drawdown |
| **O-5** | Authorization mode for Phase 8 — `manual` or `semi`? | Recommendation: `manual` for the first two weeks live |
| **O-6** | Monthly budget ceiling? | Baseline ≈ $99 Alpaca SIP data + $25 Supabase + ~$25 Fly = **~$150/mo** before any trading P&L. Notifications are $0 (Section 13). The strategy must clear this before it earns anything |
| **O-7** | Does the operator have (or qualify for) a BlackRock Advisor Center account? | Determines whether Section 19.2 is usable. The system MUST NOT depend on it either way (R-19.2.a) |
| **O-8** | Tax situation — is §475(f) mark-to-market worth exploring? | Deadline-bound; needs a CPA (R-18.d) |

---

## 22. Glossary

| Term | Meaning |
|---|---|
| **ADV** | Average daily volume |
| **ATR** | Average True Range — volatility measure used to scale stops and targets |
| **Bracket order** | Entry plus attached take-profit and stop-loss, managed broker-side |
| **Deflated Sharpe** | Sharpe ratio adjusted for the number of strategy variants tested; corrects selection bias |
| **Embargo** | Dropping samples immediately after a test window to prevent serial-correlation leakage |
| **LULD** | Limit Up-Limit Down — the volatility halt mechanism on US equities |
| **Meta-labelling** | A second model that decides whether to act on a primary model's signal, and how large |
| **Participation rate** | Your order size as a fraction of market volume over a period |
| **PDT** | Pattern Day Trader — retired 2026-06-04 (Section 2.2) |
| **PSI** | Population Stability Index — measures distribution drift between training and live data |
| **Purging** | Removing training samples whose labels overlap the test period |
| **RVOL** | Relative volume vs a historical same-time-of-day baseline |
| **SIP** | Securities Information Processor — the consolidated US market data tape |
| **Slippage** | Difference between the price you decided at and the price you actually got |
| **Triple barrier** | Labelling by which of profit-target / stop-loss / time-limit is hit first |
| **Walk-forward** | Validation that always trains on the past and tests on the future |

---

## Appendix A — The ten things most likely to sink this project

1. **Look-ahead bias in the backtest.** Produces a beautiful equity curve and a real loss. Mitigation:
   R-8.2.a/b and the golden tests.
2. **Training/serving skew.** Features computed differently in training and live. Mitigation: R-4.4.a and
   the parity test (R-16.4.a).
3. **Overfitting through repeated experimentation.** Mitigation: deflated Sharpe, experiment logging, and the
   sacred holdout (R-9.5.c/d).
4. **Underestimating costs.** Spread + slippage + fees quietly consume the edge. Mitigation: explicit cost
   modelling and the cost-drag metric (R-2.1.a), calibrated against live fills (R-16.6.a).
5. **Survivorship bias.** Mitigation: R-5.a, R-9.5.a.
6. **Two engines running at once.** Duplicate orders, unbounded size. Mitigation: R-3.1.a lease + CI check.
7. **A kill switch that was never tested.** Mitigation: the weekly automated drill (R-16.5.a).
8. **Silent data gaps** producing wrong features and wrong trades. Mitigation: R-11.2.a, staleness checks.
9. **Scaling up after a good month.** Variance, not skill. Mitigation: R-10.4.a's three-month minimum.
10. **Skipping a gate because the model "looks good."** Mitigation: gates are code, and there is no override
    flag (R-9.7.a). If you want one, that is the signal to stop.

---

## Appendix B — First tasks for the implementing session

Start here. Do not skip ahead.

1. Read Sections 1–4 completely.
2. Answer or flag the open items in Section 21 with the operator — especially **O-3** (equities vs options),
   which changes scope substantially.
3. Create `docs/decisions/0001-record-architecture-decisions.md`.
4. Scaffold the repo per Section 4.4. Nothing clever — directories, `pyproject.toml`, `package.json`,
   Dockerfiles, `fly.toml`, GH Actions workflow.
5. Stand up Supabase; write the Alembic migration for Section 5's schema, including the append-only trigger
   on `audit_log` (R-5.b).
6. Create the Telegram bot via BotFather, capture the token and your `chat_id`, and set the webhook secret.
   No carrier registration, no campaign, no waiting (Section 13.1).
7. Open an Alpaca account; generate **paper** keys; configure `.mcp.json` per 19.1.
8. Run the MCP proof of concept (Phase 0): paper bracket order placed, filled, inspected, closed.
9. Get CI green. Commit. **Stop at Gate 0** and report status.

**A note on sequencing, for whoever builds this:** the temptation will be to write the trading engine early —
it is the interesting part. Do not. The engine is worthless without a trustworthy backtester, and a
backtester is worthless without clean point-in-time data. Every phase here exists because the one after it
would otherwise be built on numbers that cannot be trusted. The discipline *is* the product.
