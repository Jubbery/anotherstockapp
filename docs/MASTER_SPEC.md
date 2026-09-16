# Atlas — Master Specification

**Single-tenant algorithmic day-trading platform**
Version 1.0 · 2026-09-16 · Status: **Normative. This document is the source of truth.**

---

## 0. Front matter

### 0.1 What this document is

A build specification written as a handoff. The reader is a competent engineer (or an agent) who has
not seen this project before and may not have a trading background. Everything needed to build Atlas
is here or referenced from here. Where this document and any other artifact disagree, **this document
wins** until an ADR supersedes it (§0.5).

### 0.2 Conformance language

| Word | Meaning |
|---|---|
| **MUST** / **MUST NOT** | Absolute requirement. Violating it is a defect, not a trade-off. Blocks the phase gate. |
| **SHOULD** / **SHOULD NOT** | Strong default. Deviating requires an ADR (§0.5). |
| **MAY** | Genuinely optional. Build it if it helps; leave it out if it doesn't. |

Numbered rules use `R-<section>.<subsection>.<letter>` — e.g. `R-12.3.a`. They are indexed in
**Appendix D**. Cite the rule ID in code comments, commit messages, and test names where a rule is
being enforced. A grep for a rule ID MUST find both its definition and its enforcement.

### 0.3 Hard gates

🔴 **HARD GATE** markers separate build phases (§20). At a gate you stop, run the acceptance criteria,
write the status report, and wait. You do not start the next phase because the current one "is basically
done". The gates exist because every phase after Phase 4 can lose real money, and the only cheap place
to find out the data is wrong is before the engine is built on top of it.

### 0.4 Reading order

If you are starting from zero, read in this order:

1. **Appendix B** — domain primer and glossary. Skip only if you have traded professionally.
2. **§1–§4** — what this is, what it is not, the rules that never bend, and the architecture.
3. **§20** — the phase plan, so you know what you are actually being asked to build first.
4. The section for the phase you are on.

Everything else is reference. Do not read the whole document before writing the first line of code;
do not write a line of code in a safety-critical area (§3.4) without reading its section in full.

### 0.5 Deviations and ADRs

Any deviation from a MUST, or from a SHOULD, gets an **Architecture Decision Record** in
`docs/decisions/NNNN-short-title.md`, numbered sequentially, using the template in
`docs/decisions/0000-template.md`. An ADR states: context, the rule being deviated from, the decision,
the consequences, and what would cause us to revisit. An undocumented deviation is a defect.

**R-0.5.a** — A `MUST` MUST NOT be weakened to unblock a phase. If a MUST is blocking you, that is
information about the design. Raise it with the operator and write the ADR. Silently relaxing a risk
rule to get a green test is the single most dangerous thing you can do in this repository.

### 0.6 Change log

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-09-16 | Initial specification. |

### 0.7 Contents

| § | Section | § | Section |
|---|---|---|---|
| 1 | [Purpose and audience](#1-purpose-and-audience) | 12 | [The risk governor](#12-the-risk-governor) |
| 2 | [Scope](#2-scope) | 13 | [Control plane](#13-control-plane-authorization-kill-switch-notifications) |
| 3 | [Non-negotiables](#3-non-negotiables) | 14 | [API surface](#14-api-surface) |
| 4 | [System architecture](#4-system-architecture) | 15 | [Frontend](#15-frontend) |
| 5 | [Repository, stack, conventions](#5-repository-stack-and-conventions) | 16 | [Security](#16-security) |
| 6 | [Data platform](#6-data-platform) | 17 | [Observability and audit](#17-observability-and-audit) |
| 7 | [Stage A — 8,000 → 50](#7-stage-a--deterministic-narrowing-8000--50) | 18 | [Testing and CI](#18-testing-and-ci) |
| 8 | [Backtester and simulation](#8-backtester-and-simulation) | 19 | [Tooling: MCP boundaries](#19-tooling-the-alpaca-mcp-and-other-connectors) |
| 9 | [The machine learning layer](#9-the-machine-learning-layer) | 20 | [Build phases](#20-build-phases) |
| 10 | [Execution engine](#10-execution-engine) | 21 | [Open items for the operator](#21-open-items-for-the-operator) |
| 11 | [Configuration and environments](#11-configuration-and-environments) | | |

**Appendices** — [A Configuration reference](#appendix-a--configuration-reference) ·
[B Domain primer and glossary](#appendix-b--domain-primer-and-glossary) ·
[C Database schema](#appendix-c--database-schema-outline) ·
[D Rule index](#appendix-d--rule-index) ·
[E Cost and fill model](#appendix-e--cost-and-fill-model-reference) ·
[F Runbooks](#appendix-f--runbooks) ·
[G A day, concretely](#appendix-g--a-day-concretely)

The sections that carry the most risk, and that reward the closest reading, are
**§9.1** (how ML silently fails on financial data), **§12** (the risk governor), and **§13.2** (the
kill switch).

---

## 1. Purpose and audience

### 1.1 The one-sentence version

Atlas scans the entire liquid US equity market each morning, narrows it to fifty names by deterministic
rules and to ten by a learned ranker, day-trades those ten inside an explicit authorization that expires
within twenty-four hours, and can be stopped completely from a phone in under ten seconds.

### 1.2 Who operates it

One person. The **operator** is the sole user, the sole owner of capital, and the sole approver of live
trading. There are no other tenants, no roles, no sharing, no multi-user features. This is a deliberate
simplification and it propagates: authentication is single-account (§16.2), the database has one owning
user (Appendix C), and there is no permissions model beyond "the operator, or not the operator".

**R-1.2.a** — Atlas MUST NOT accept funds from, trade on behalf of, or expose an account interface to
any party other than the operator. Multi-tenancy is out of scope permanently, not merely deferred.

### 1.3 What success looks like

Success is **not** a profitable backtest. A profitable backtest is the cheapest artifact in
quantitative finance and it is usually wrong. Success is:

1. A data layer whose point-in-time correctness can be demonstrated, not asserted (§6.4).
2. A backtester whose fills a reasonable skeptic would accept (§8).
3. An ML layer that beats a no-ML baseline by a margin that survives the promotion gates in §9.7 —
   or an honest conclusion that it does not, and its removal.
4. An execution path that cannot place an order that violates a risk rule, proven by exhaustive
   branch coverage rather than by inspection (§12).
5. A kill switch the operator has personally used, in a drill, within the last seven days (§13.3).
6. Live trading that is boring.

### 1.4 What the operator actually wants from the UI

Three questions, answerable in under five seconds each, on a phone:

- *What is it doing right now, and what is it about to do?*
- *How much am I up or down today, and what is my worst case from here?*
- *How do I make it stop?*

Everything else in the frontend is secondary to these three. §15 elaborates.

### 1.5 Explicit statement about risk

This system trades a real brokerage account with the operator's own money. Day trading is
overwhelmingly loss-making for individual participants; the base rate for this category of project is
that it loses money net of costs. The specification is built around that expectation: the phase plan
front-loads the parts that tell you the truth (data, backtester, honest validation) and defers the
parts that spend money (the engine, then live) behind gates. If Atlas reaches Phase 8 and the evidence
says the edge is not there, **not going live is a successful outcome of this project**, and §20.9 says
so in its acceptance criteria.

Nothing in this document is financial advice, and nothing in it should be read as a claim that the
described approach is profitable.

---

## 2. Scope

### 2.1 In scope

- US-listed **common stock and ETFs** traded on NYSE, NASDAQ, and NYSE American/Arca.
- **Intraday only** — every position opened during a session is closed before that session's close
  (§12.4). No overnight exposure, ever.
- **Long and short.** Shorting is permitted subject to locate/shortability checks (§7.3, §12.3).
- **Regular trading hours (RTH)**, 09:30–16:00 America/New_York, plus a pre-open preparation window.
- One brokerage account at Alpaca, in exactly one of two environments: paper or live (§11.1).

### 2.2 Out of scope

Permanently, unless a future ADR reopens it:

- **Options, futures, crypto, forex, fixed income.** See §2.3.
- Overnight, swing, or multi-day positions.
- Extended-hours trading (pre-market / after-hours). Data from those sessions is *used* as a feature
  (§7.2) but no order is ever routed outside RTH.
- Margin beyond the standard intraday buying power Alpaca extends to a cash-funded account, and no
  deliberate use of leverage as a strategy lever (§12.2 caps gross exposure well below the available
  limit).
- Any form of market making, latency arbitrage, or strategy whose viability depends on sub-100ms
  round-trip times. Atlas runs on a cloud VM behind a REST/WebSocket API; it is a minutes-to-hours
  holding-period system, not a microstructure system.
- Managing external capital, publishing signals, or any customer-facing product.

### 2.3 Resolved scope decision: equities, not options

The original brief used the phrase "day trade stock options" alongside "scans ~8,000 US equities".
Those are two different systems. **Atlas trades equities.** Options are out of scope. Recorded as
**ADR-0002**.

Rationale, because this will be asked again:

- An options system needs a second pricing dimension (implied volatility surface), a Greeks-based risk
  model, and assignment/exercise handling. The risk governor in §12 would roughly triple in size, and
  §12 is the part that must be exhaustively verified.
- Option spreads are far wider in percentage terms than equity spreads. The Stage A liquidity filters
  (§7.3) that make the equity universe tradeable would eliminate most of the options universe, and the
  ones that survive are the ones everyone else is already trading.
- The ML labelling scheme in §9.3 assumes a price series with a continuous, non-expiring underlying.
  Options require handling expiry as a hard barrier and rolling between contracts, which changes the
  label definition and the backtest fill model.
- Alpaca's options support is a different API surface with different data entitlements, which would
  fork §6 and §10.

If the operator later wants options exposure, that is a **new project** that reuses Atlas's data layer
and control plane, not a feature added to this one.

### 2.4 Resolved scope decision: PDT

The operator states that the Pattern Day Trader rule was retired in June 2026. Atlas is specified to
operate without a PDT constraint. However:

**R-2.4.a** — The day-trade counter and its limit MUST be implemented as a risk rule (`R-12.2.ad`) that
is *configuration-gated*, defaulting to **disabled** with the limit recorded in config, not deleted
from the codebase. Regulatory reversals happen, and re-enabling a config flag is a five-minute change
where re-implementing a deleted risk rule under time pressure is not.

**R-2.4.b** — Before Phase 8 (live), the operator MUST confirm the current PDT status directly with
Alpaca and record the confirmation, with date, in `docs/SOURCES.md`. This specification's assumption is
not evidence.

### 2.5 Non-goals that sound like goals

- **Maximum returns.** Atlas optimizes for *not being wrong in an expensive way*. Every default in this
  spec is the conservative one.
- **Full automation.** The operator is deliberately in the loop once per day, at the authorization step
  (§13.1). This is not a limitation to be engineered away.
- **Generality.** Do not build abstractions for strategies Atlas does not have, brokers it does not
  use, or asset classes §2.2 excludes. A second broker is a `BrokerPort` implementation (§4.3) and that
  is the entire extent of the generality budget.

---

## 3. Non-negotiables

These are the rules that do not bend. They are repeated here, out of their home sections, because a
reader who only reads one section should read this one.

### 3.1 Live trading is the last thing built

**R-3.1.a** — Live trading is **Phase 8**, behind the eight gates in §20.9. Every phase before it runs
against Alpaca **paper**. There is no "just a small live test" before Phase 8.

**R-3.1.b** — `ALPACA_ENV` MUST be set explicitly to `paper` or `live`. There is no default. A missing
or unrecognized value MUST raise at process startup, before any network call, any database connection,
and any scheduler registration. See §11.1.

**R-3.1.c** — Live API credentials MUST exist only in the Fly.io secret store for the production
`engine` and `api` apps. They MUST NOT appear in CI, `.env.example`, developer machines, the MCP
configuration, backtest fixtures, or any file in the repository. See §16.

### 3.2 One order path

**R-3.2.a** — Exactly one function in the codebase calls the broker's order-placement API. Every order
reaches it through the risk governor. There is no bypass, no `force=True`, no "emergency manual order"
helper. See §10.1 and §12.

**R-3.2.b** — The risk governor (`services/engine/risk/`) MUST have **100% branch coverage**, enforced
in CI as a hard failure. Its functions MUST be pure: inputs in, decision out, no I/O, no clock reads,
no randomness. The clock is an input. See §12.6.

### 3.3 The operator can always stop it

**R-3.3.a** — The operator MUST be able to halt all trading from a phone, and Atlas MUST reach a state
where no new orders can be placed and all working orders are cancelled, within **10 seconds p99**,
measured end-to-end from the moment the operator's message is sent. See §13.2.

**R-3.3.b** — The kill switch MUST be exercised in a **weekly drill** against the paper environment.
A drill result older than 8 days MUST raise a warning to the operator and MUST block promotion to, or
continuation of, live trading. See §13.3.

**R-3.3.c** — The kill switch MUST have at least **three independent activation paths** that do not
share a single point of failure (§13.2.2), and at least one MUST work when the Atlas frontend is
completely down.

### 3.4 Authorization expires

**R-3.4.a** — Atlas MUST NOT place any order that is not covered by an unexpired, unrevoked
authorization grant. The engine checks this per order, at submission time, not at session start.

**R-3.4.b** — No grant may have a lifetime exceeding **24 hours**. This is enforced in three places:
a database `CHECK` constraint, the API validator, and the risk governor. See §13.1.

**R-3.4.c** — Grants MUST NOT auto-renew, and there MUST be no "remember me", "always allow", or
standing-authorization mechanism. Each trading day requires a fresh, deliberate act by the operator.

### 3.5 The data must be honest

**R-3.5.a** — Every feature used at decision time MUST be computable from information that was
available at that time. Point-in-time correctness is enforced by construction (§6.4) and verified by
the leakage test suite (§9.1, §18.4).

**R-3.5.b** — Feature computation code MUST be imported by both the training path and the live path
from a single module. It MUST NOT be reimplemented, transcribed, or ported between them. See §4.4.

### 3.6 Money is not a float

**R-3.6.a** — All monetary quantities MUST be `decimal.Decimal` in Python and `NUMERIC` in Postgres.
`float` MUST NOT appear in any type signature that carries money, a price, or a quantity that gets
multiplied by a price. Statistical and ML code MAY use floats internally on *returns and features*;
the boundary is enforced at the type level (§5.5).

### 3.7 Everything that matters is audited

**R-3.7.a** — Every write that changes money, a position, or an authorization state MUST occur inside a
database transaction that also writes an `audit_log` row. Not "should also log" — the same transaction.
If the audit write fails, the money write rolls back.

**R-3.7.b** — `audit_log` is append-only, enforced by a database trigger that rejects `UPDATE` and
`DELETE` regardless of role. See §17.4.

### 3.8 The MCP server stays out of the engine

**R-3.8.a** — The Alpaca MCP server, and every other MCP server or connector, MUST NOT be referenced
anywhere under `services/`. MCP is a research and operator tool. The engine reaches Alpaca through
`BrokerPort` and `MarketDataPort` so that order paths remain deterministic, idempotent, and
risk-checked. See §19.3.

---

## 4. System architecture

### 4.1 Shape

Atlas is four deployable units and one shared library.

```
                      ┌──────────────────────────────────────┐
   operator's phone   │            Vercel                    │
   ────────────────►  │  web/   Next.js 15 + TS + Manrope    │
        │             └───────────────┬──────────────────────┘
        │                             │ HTTPS, generated client
        │                             ▼
        │             ┌──────────────────────────────────────┐
        │             │            Fly.io                     │
        │  Telegram   │  api/     FastAPI  (control plane)   │
        ├────────────►│           ├─ auth, authorization      │
        │  Twilio SMS │           ├─ kill switch endpoint     │
        │  (webhooks) │           ├─ read models for UI       │
        │             │           └─ inbound webhooks         │
        │             │                                       │
        │             │  engine/  asyncio  (trading loop)     │
        │             │           ├─ scanner  (Stage A)       │
        │             │           ├─ ranker   (Stage B/C)     │
        │             │           ├─ risk governor            │
        │             │           ├─ order manager            │
        │             │           └─ position/PnL tracker     │
        │             │                                       │
        │             │  worker/  ingest + training jobs      │
        │             └───────┬──────────────────┬────────────┘
        │                     │                  │
        │                     ▼                  ▼
        │      ┌──────────────────────┐   ┌──────────────────┐
        │      │  Supabase            │   │  Alpaca          │
        │      │  Postgres + Storage  │   │  Trading + Data  │
        │      │  Realtime + Auth     │   │  REST + WS       │
        │      └──────────────────────┘   └──────────────────┘
        │
        └──── kill switch reaches engine via three paths (§13.2.2)
```

### 4.2 Deployable units

| Unit | Runtime | Hosting | Scaling | Purpose |
|---|---|---|---|---|
| `web/` | Next.js 15, TypeScript, React Server Components | Vercel | Edge/serverless | Operator UI |
| `services/api/` | Python 3.12, FastAPI, uvicorn | Fly.io | 1–2 machines, always on | Control plane, read models, webhooks |
| `services/engine/` | Python 3.12, asyncio | Fly.io | **Exactly 1 machine** | Scan, decide, trade, track |
| `services/worker/` | Python 3.12 | Fly.io Machines (ephemeral) | 0–N, on demand | Bulk ingest, training, backtests, nightly jobs |
| `libs/atlas_core/` | Python 3.12 package | — | — | Shared domain, features, contracts |

**R-4.2.a** — The engine MUST run as a **singleton**. Exactly one instance may hold the trading lease
at a time. Enforced by a Postgres advisory lock (`pg_try_advisory_lock`) acquired at startup and held
for the process lifetime; a second instance that cannot acquire the lock MUST log and exit non-zero,
not wait. Two engines placing orders against one account is an unbounded-loss failure mode.

**R-4.2.b** — The API MUST NOT place orders. It writes *intents* and *control state* to the database;
the engine reads them. The API's Alpaca credentials, if any, MUST be read-scoped. This keeps R-3.2.a
true even when the API has a bug.

**R-4.2.c** — The engine MUST be always-on from 08:00 to 16:30 America/New_York on trading days, and
MAY be stopped outside that window. Fly.io `auto_stop_machines` MUST be disabled for the engine app;
a cold start in the middle of a position is not acceptable.

### 4.3 Ports and adapters

The engine is written against interfaces, not vendors. These live in `libs/atlas_core/ports/` as
`Protocol` classes and are the only place a vendor concept may cross into domain code.

| Port | Responsibility | Production adapter |
|---|---|---|
| `BrokerPort` | submit / cancel / replace orders, read account, read positions, stream order updates | `AlpacaBrokerAdapter` |
| `MarketDataPort` | historical bars, snapshots, quotes, stream of trades/quotes/bars | `AlpacaDataAdapter` |
| `ReferenceDataPort` | tradeable asset list, shortability, corporate actions, market calendar | `AlpacaReferenceAdapter` |
| `ClockPort` | current time, market session state | `SystemClock` / `SimulatedClock` |
| `StorePort` | domain persistence (orders, positions, runs, audit) | `PostgresStore` |
| `NotifierPort` | outbound SMS / email / push | `TwilioNotifier`, `ResendNotifier` |
| `ModelPort` | load model artifact, predict | `LightGBMModel` |

**R-4.3.a** — Domain and decision code MUST depend only on ports. `import alpaca` MUST NOT appear
outside `services/*/adapters/`. Enforced by an import-linter contract in CI (§18.6).

**R-4.3.b** — Every port MUST have a deterministic fake in `libs/atlas_core/testing/` used by unit
tests, and the backtester MUST be built from the same fakes (§8.2). The backtester is not a separate
codebase; it is the engine driven by simulated ports.

This last point is the single most important architectural decision in the document. It is what makes
"the backtest and the live system behave identically" a structural property rather than a hope.

### 4.4 Shared code and the feature parity boundary

`libs/atlas_core/` contains, and is the *only* place that contains:

```
libs/atlas_core/
  domain/        Symbol, Money, Quantity, Side, OrderIntent, Position, Bar, Quote …
  features/      feature computation — imported by training AND live
  labels/        triple-barrier labelling
  rules/         Stage A predicates (§7.3) — imported by scanner AND backtester AND label gen
  ports/         Protocol definitions
  costs/         fee, spread, slippage models (§8.3)
  calendar/      market calendar, session arithmetic
  config/        typed settings (§11)
  testing/       deterministic fakes, fixture builders
```

**R-4.4.a** — Feature code MUST be imported by both the training path and the live path from
`libs/atlas_core/features/`. It MUST NOT be duplicated. Any duplication is a defect at the same severity
as a risk-rule bypass, because it produces a model whose live inputs silently differ from its training
inputs — and that failure is invisible until it costs money.

**R-4.4.b** — Stage A rule predicates MUST likewise be shared between the live scanner, the backtester,
and label generation. A name that Stage A would have rejected MUST NOT contribute a training label.

**R-4.4.c** — A **parity test** MUST exist that computes every feature for a fixed set of
(symbol, timestamp) pairs through the training path and through the live path and asserts bitwise-equal
results (or equality to 1e-12 for floats). It runs in CI on every commit. See §9.2.4.

### 4.5 Data flow: one trading day

Times are America/New_York.

| Time | Actor | What happens |
|---|---|---|
| 04:00 | worker | Nightly ingest completes: prior-day bars, corporate actions, asset list, calendar. §6.5 |
| 04:30 | worker | Universe snapshot written for today (PIT, §6.4.2). Feature backfill for daily features. |
| 05:00 | worker | Data quality gate runs. Failure here blocks the day (§6.7). |
| 08:00 | engine | Boots, acquires lease, loads model artifact, verifies model/feature versions match. |
| 08:45 | engine | **Stage A** scan: ~8,000 → 50. Writes `scan_run` + `scan_candidate` rows. §7 |
| 09:00 | engine | **Stage B** rank: 50 → 10. Writes `rank_run` + `rank_candidate` rows with scores. §9.5 |
| 09:05 | api → operator | Notification: "10 candidates ready. Authorize?" with a deep link. §13.4 |
| — | operator | Reviews the ten, sets a capital cap, authorizes. Grant expires ≤24h. §13.1 |
| 09:30 | engine | Market opens. Engine subscribes to minute bars + quotes for the ten names. |
| 09:45 | engine | Entry window opens (no trades in the first 15 minutes — §7.4, `opening_range_minutes`). |
| 09:45–15:30 | engine | **Stage C** gates each candidate entry; risk governor gates each order. §9.6, §12 |
| 15:45 | engine | No new entries (`no_new_entries_after`). §12.4 |
| 15:55 | engine | Force-flatten any open position with marketable orders. §12.4 |
| 16:00 | engine | Close. Reconcile fills vs broker. Write `pnl_daily`. |
| 16:05 | api → operator | End-of-day summary notification. §13.4 |
| 16:30 | engine | Enters idle. Lease released. |
| 17:00 | worker | Today's minute bars flushed from hot table to Parquet in Storage. §6.3.3 |
| Weekly | worker | Retraining candidate produced; promotion gates evaluated (§9.7). Kill-switch drill (§13.3). |

Appendix G walks the same day with concrete numbers.

### 4.6 Engine state machine

```
                 ┌──────┐
                 │ BOOT │ acquire lease, load config, verify model
                 └──┬───┘
                    ▼
               ┌─────────┐  data quality gate, calendar check
               │ WARMUP  │
               └──┬──────┘
                  ▼
               ┌──────┐  Stage A then Stage B
               │ SCAN │
               └──┬───┘
                  ▼
              ┌───────┐  waiting for operator authorization
              │ ARMED │◄──────────────┐
              └──┬────┘               │ grant renewed
                 │ grant valid        │
                 ▼                    │
            ┌──────────┐   grant expires / revoked
            │ TRADING  │──────────────┘
            └──┬───┬───┘
               │   │ 15:45
               │   ▼
               │ ┌──────────────┐
               │ │ WINDING_DOWN │ no new entries, manage exits
               │ └──────┬───────┘
               │        │ 15:55 force-flatten
               │        ▼
               │    ┌──────┐
               │    │ FLAT │ reconcile, report
               │    └──────┘
               │
               │ kill switch, from ANY state
               ▼
          ┌────────┐
          │ HALTED │ cancel all, optionally flatten, refuse everything
          └────────┘   only the operator can leave this state
```

**R-4.6.a** — `HALTED` MUST be reachable from every state, MUST be the highest-priority transition, and
MUST NOT be exitable by any automatic process. Leaving `HALTED` requires an explicit operator action
recorded in `audit_log`.

**R-4.6.b** — State transitions MUST be persisted to `engine_state` with timestamps before side effects
are taken, so that a crashed engine restarts into a known state rather than a guessed one.

**R-4.6.c** — On restart with open positions, the engine MUST enter `WINDING_DOWN`, not `TRADING`. It
reconciles against the broker as the source of truth (§10.6), manages existing positions to exit, and
MUST NOT open new positions until the operator re-authorizes.

### 4.7 Why this shape

- **Engine separate from API** because the trading loop must not be interrupted by an HTTP request
  storm, a Vercel preview deploy, or a webhook retry, and because it lets the API be stateless and
  horizontally scaled while the engine stays a singleton (R-4.2.a).
- **Database as the control-plane bus** because Supabase gives us `LISTEN/NOTIFY` and Realtime for
  free, the state is durable and auditable by construction, and a message bus would be a fifth thing
  to operate for one user.
- **Worker separate** because training and bulk ingest are memory-hungry and bursty, and must never
  compete for CPU with the trading loop.
- **No Kubernetes, no queue broker, no microservice mesh.** One user, one account. Operational
  simplicity is a risk control: every component is a component that can fail at 15:52.

---

## 5. Repository, stack, and conventions

### 5.1 Layout

```
atlas/
  CLAUDE.md                     working agreements for agents
  README.md                     orientation, 30 lines, points here
  docs/
    MASTER_SPEC.md              this document
    SOURCES.md                  every external fact + where it came from + when
    RUNBOOKS.md                 operational procedures (Appendix F expanded)
    decisions/                  ADRs
    research/                   dated research notes (R-19.1.c)
  libs/
    atlas_core/                 shared domain library (§4.4)
  services/
    api/                        FastAPI control plane
      routes/  schemas/  deps/  adapters/
    engine/
      loop.py                   the state machine (§4.6)
      scanner/                  Stage A (§7)
      ranking/                  Stage B + C (§9.5, §9.6)
      risk/                     RISK GOVERNOR — 100% branch coverage (§12)
      execution/                order manager, idempotency, reconciliation (§10)
      positions/                position + PnL tracking
      adapters/                 Alpaca, Postgres, Twilio, Resend
    worker/
      ingest/                   bulk historical + nightly (§6.5)
      training/                 label gen, CV, training, promotion (§9)
      backtest/                 backtest runner (§8)
      jobs/                     scheduled maintenance
  web/
    app/                        Next.js 15 App Router
    components/
    lib/api/                    GENERATED from OpenAPI — do not hand-edit (§15.6)
  db/
    migrations/                 versioned SQL, forward-only
    policies/                   RLS policies
    triggers/                   audit_log append-only trigger
  tests/
    unit/  integration/  property/  golden/  leakage/  e2e/
  ops/
    fly/                        fly.toml per app
    github/                     CI workflows
  .mcp.json                     Alpaca MCP — PAPER KEYS ONLY (§19.2)
  pyproject.toml
```

### 5.2 Stack, pinned

| Layer | Choice | Notes |
|---|---|---|
| Frontend | Next.js 15 (App Router), TypeScript `strict: true`, React 19 | Vercel |
| Font | **Manrope** via `next/font/google`, variable weight | §15.2 |
| Styling | Tailwind CSS v4 + CSS variables for theme tokens | §15.2 |
| Charts | Lightweight Charts (TradingView) for price; Recharts for everything else | §15.4 |
| Backend | Python 3.12, FastAPI, uvicorn, asyncio | Fly.io |
| Validation | Pydantic v2 everywhere at boundaries | |
| DB access | asyncpg + SQL. **No ORM.** | §5.6 |
| Migrations | Plain SQL, forward-only, applied by CI | `db/migrations/NNNN_*.sql` |
| Database | Supabase Postgres 15+ | RLS on, §16.4 |
| Blob | Supabase Storage | Parquet bar archive, model artifacts |
| ML | LightGBM, scikit-learn, pandas, numpy, pyarrow, DuckDB | §9 |
| Experiment tracking | MLflow (self-hosted on Fly volume) or filesystem+DB registry | §9.8 |
| Broker/data | Alpaca `alpaca-py` | §6.2, §19.2 |
| SMS | Twilio | §13.4 |
| Email | Resend | §13.4 |
| Inbound control | Telegram Bot API + Twilio inbound SMS | §13.2.2 |
| Lint/format | `ruff` (lint + format), `mypy --strict` on `services/` and `libs/` | §5.5 |
| Test | `pytest`, `pytest-asyncio`, `hypothesis`, `pytest-cov`, `freezegun` | §18 |
| TS tooling | `eslint`, `prettier`, `vitest`, `playwright` | §18.5 |

### 5.3 Naming and language conventions

- Python: `snake_case`, modules singular, no `utils.py` — name the thing it does.
- SQL: `snake_case`, plural table names, singular column names, `_at` suffix for timestamps,
  `_id` suffix for foreign keys, `NUMERIC` for money.
- TypeScript: `camelCase` for values, `PascalCase` for types/components, no default exports except
  Next.js pages.
- Rule enforcement sites carry a comment `# R-12.3.a` so the rule ID is greppable.

### 5.4 Time

**R-5.4.a** — All timestamps in storage, in transit, and in domain objects MUST be timezone-aware UTC.
A naive `datetime` MUST NOT cross a function boundary. Enforced by a `mypy` plugin or a
runtime assertion in `libs/atlas_core/domain/time.py`.

**R-5.4.b** — `America/New_York` appears **only** at the display layer and in market-calendar
arithmetic, and any rendered local time MUST be labelled with its timezone in the UI. A time shown
without a label is a defect.

**R-5.4.c** — Market session boundaries MUST come from the exchange calendar (`ReferenceDataPort`),
never from hardcoded 09:30/16:00 constants. Half-days exist; 2026 has several; a hardcoded close time
is a position held overnight.

### 5.5 Types and money

**R-5.5.a** — `Money` and `Price` are distinct newtypes over `Decimal` in
`libs/atlas_core/domain/money.py`. Multiplication of `Price × Quantity` returns `Money`; adding
`Price` to `Money` is a type error. `float` MUST NOT be accepted by any constructor.

**R-5.5.b** — Decimal context: `ROUND_HALF_EVEN`, 28 significant digits. Prices are quantized to the
symbol's tick size (§10.4) at the point of order construction, not earlier.

**R-5.5.c** — `mypy --strict` MUST pass on `services/` and `libs/` with **zero** `# type: ignore`
outside `adapters/`, where third-party stubs may be missing. Each ignore in `adapters/` carries a
comment naming the library and the reason.

### 5.6 Why no ORM

The queries that matter here are analytical (time-series windows, `DISTINCT ON`, `LATERAL` joins over
bars) and transactional in a way where the exact locking behaviour matters (order state transitions,
§10.3). An ORM obscures both. SQL lives in `*.sql` files or module-level constants, is linted by
`sqlfluff`, and every query that participates in a money-changing transaction has its isolation level
stated explicitly.

### 5.7 Dependencies

**R-5.7.a** — All dependencies pinned to exact versions with a lockfile (`uv.lock` /
`package-lock.json`), committed. Renovate/Dependabot MAY open PRs; they MUST NOT auto-merge into a
branch that deploys the engine.

**R-5.7.b** — Adding a dependency to `libs/atlas_core/` or `services/engine/risk/` requires an ADR.
Those two are the blast radius; the dependency graph there should be almost empty.

---

## 6. Data platform

Everything downstream is a function of this section being right. Budget accordingly: Phase 1 is
expected to take longer than it "should", and the acceptance criteria in §20.2 are deliberately harsh.

### 6.1 The data we need

| Dataset | Grain | History | Used by |
|---|---|---|---|
| Daily bars | symbol × day, OHLCV + VWAP + trade count | 10 years | Stage A, daily features, labels |
| Minute bars | symbol × minute, OHLCV + VWAP + trade count | 3 years (top ~1,500 names), current day (all) | Stage B/C features, backtest, execution |
| Quotes (NBBO) | symbol × event | live only + sampled snapshots | spread filter, execution, fill model calibration |
| Trades | symbol × event | live only | execution, microstructure features (Phase 4+) |
| Asset master | symbol | current + daily snapshots | universe construction, shortability |
| Corporate actions | symbol × event | 10 years | adjustment factors, PIT correctness |
| Market calendar | date | 10 years + forward | session arithmetic, half-days |
| Account/position state | account × time | live | risk governor, reconciliation |

### 6.2 Source: Alpaca, and the feed question

Atlas uses Alpaca for both brokerage and market data. One decision must be made before Phase 1 and it
has a monthly cost:

**IEX feed** (included) carries only trades/quotes that printed on IEX — roughly 2–3% of consolidated
volume. **SIP feed** (paid, "Algo Trader Plus" tier) carries the full consolidated tape.

**R-6.2.a** — Atlas MUST use the **SIP** feed. A scanner ranking 8,000 symbols by dollar volume and
relative volume on 2–3% of the tape is ranking noise, and a spread filter computed from IEX-only quotes
does not describe the spread the order will actually cross. Training on IEX and trading on SIP would
also violate R-3.5.b in spirit: the feature distributions differ.

**R-6.2.b** — The data feed in use MUST be recorded in every `scan_run`, `rank_run`, and model artifact
(`feed: sip|iex`). A model trained on one feed MUST NOT be promoted for use with the other; the
promotion gate (§9.7) checks this.

**Open item O-1** (§21): confirm current pricing and entitlements with Alpaca and record in
`docs/SOURCES.md`. If SIP is not available, the honest response is to shrink the universe to names
where IEX coverage is adequate and to say so — not to pretend the scan is market-wide.

**R-6.2.c** — Alpaca rate limits MUST be respected by a shared token-bucket limiter in the adapter,
with the limit read from config, exponential backoff with jitter on 429, and a circuit breaker that
trips to `HALTED` if the broker API error rate exceeds the threshold in §11.3. The limiter MUST be
shared across all tasks in a process.

### 6.3 Storage design

8,000 symbols × 390 minutes × 252 days ≈ **786 million minute bars per year**. Putting three years of
that in Supabase Postgres is a mistake: it is expensive, slow to scan, and the access pattern is
analytical. The split:

#### 6.3.1 Postgres holds

- `bars_daily` — all symbols, 10 years. ~20M rows. Partitioned by year. This is cheap and is what
  Stage A reads.
- `bars_minute_hot` — **current trading day only**, all symbols we are watching plus the Stage A 50.
  Truncated and archived nightly (§6.5.4). ~500k–1.5M rows at any time.
- All reference, control-plane, order, position, model-registry, and audit tables.

#### 6.3.2 Supabase Storage holds

- `bars/minute/dt=YYYY-MM-DD/part-*.parquet` — the minute-bar archive, one partition per trading day,
  Zstd-compressed, columns `(symbol, ts, open, high, low, close, volume, vwap, trade_count)` with
  `symbol` dictionary-encoded and rows sorted by `(symbol, ts)`.
- `features/<feature_set_version>/dt=.../part-*.parquet` — materialized training features.
- `models/<model_id>/` — model artifact, feature list, training manifest, metrics (§9.8).
- `backtests/<run_id>/` — trade blotter, equity curve, config snapshot.

#### 6.3.3 Research reads Parquet with DuckDB

Training and backtesting query Storage directly through DuckDB (`httpfs`), not through Postgres. A
three-year minute-bar scan over a 1,500-symbol subset is seconds in DuckDB and minutes-to-never in a
managed Postgres.

**R-6.3.a** — Bar data MUST be written once and never updated in place. A correction from the vendor
creates a **new** partition version (`dt=.../v=2/`) and a row in `bar_revisions` recording what changed
and when we learned it. Rewriting history silently is how a backtest starts lying.

**R-6.3.b** — Every Parquet partition MUST have a manifest row in `bar_files` with row count, byte
size, content hash, min/max timestamp, and the ingest run that produced it. A reader MUST verify the
hash before using a partition in training.

### 6.4 Point-in-time correctness

This is §3.5 made concrete. Three mechanisms:

#### 6.4.1 Knowledge time on everything restatable

**R-6.4.a** — Any table whose contents can be restated (corporate actions, asset master, fundamentals
if ever added, vendor bar corrections) MUST carry both `effective_at` (when the fact became true in the
world) and `knowledge_at` (when Atlas learned it). Every historical query MUST filter
`knowledge_at <= as_of`. A query that reads such a table without an `as_of` MUST fail a lint check in
`tests/leakage/`.

#### 6.4.2 Universe snapshots

**R-6.4.b** — The tradeable universe MUST be snapshotted daily into `universe_snapshots`, including
symbols that later delist. Backtests and label generation MUST construct the universe for date *D*
from the snapshot taken on *D*, never from today's asset list. Using today's list is survivorship bias
and it inflates every backtest in a way that looks like skill.

**R-6.4.c** — Delisted symbols MUST be retained in `symbols` with `delisted_at` set, and their bars
MUST be retained. Deleting them is how the bias gets reintroduced.

#### 6.4.3 Split and dividend adjustment

**R-6.4.d** — Raw, unadjusted OHLCV MUST be stored. Adjustment factors are stored separately in
`corporate_actions` with `knowledge_at`, and adjusted series are **computed at read time, as of a
given date**. Storing adjusted prices means every split silently rewrites history, and a model trained
on Tuesday sees a different past than the same model trained on Monday.

**R-6.4.e** — Stage A dollar-volume and price filters (§7.3) MUST be evaluated on the prices as they
appeared on that date — i.e. unadjusted for splits occurring after that date. A $200 stock that later
split 10:1 was not a $20 stock at the time and must not be filtered as one.

#### 6.4.4 Causality

**R-6.4.f** — Every feature computed on bar series MUST use **causal** windows only — a value at time
*t* depends on bars with timestamp ≤ *t*. Centered rolling windows, `shift(-n)`, and `bfill` MUST NOT
appear in `libs/atlas_core/features/`. A static check in `tests/leakage/test_no_future_ops.py` greps
the AST for these patterns and fails the build.

**R-6.4.g** — Bar timestamps are **bar-open** convention, UTC. A bar stamped 14:31:00Z covers
[14:31:00, 14:32:00). A decision taken "at" 14:31 MUST use the bar stamped 14:30 as its most recent
complete bar. This off-by-one is the most common lookahead bug in intraday systems; the convention is
stated once here and asserted in `tests/leakage/test_bar_alignment.py`.

### 6.5 Ingest

#### 6.5.1 Bulk historical (one-time, then backfill)

**R-6.5.a** — Bulk historical ingest MUST use the Alpaca **REST API** from `services/worker/ingest/`,
not MCP tool calls (R-19.3.b). Same data, but REST gives pagination, retries, rate-limit headers, and
a resumable checkpoint.

Implementation notes:

- Use the multi-symbol bars endpoint; batch symbols (≈100 per request) and page on `next_page_token`.
- Checkpoint `(symbol_batch, start, end, page_token)` into `ingest_checkpoints` after every page so a
  crash resumes rather than restarts.
- Write Parquet directly; do not stage 786M rows through Postgres.
- Expect the full 3-year minute backfill for 1,500 symbols to take hours. Run it once, verify it, and
  never do it again casually.

#### 6.5.2 Nightly

Runs 02:00–05:00 ET on the worker:

1. Fetch prior session daily bars for the full asset list → `bars_daily`.
2. Fetch prior session minute bars for the snapshot universe → Parquet partition.
3. Fetch corporate actions since last run → `corporate_actions` with `knowledge_at = now()`.
4. Refresh asset master → diff against yesterday → `universe_snapshots` row for today, marking
   new listings, delistings, and shortability changes.
5. Refresh forward market calendar (90 days).
6. Recompute daily features for the snapshot universe → `features` / Parquet.
7. Run the data quality gate (§6.7).

#### 6.5.3 Intraday

The engine subscribes to Alpaca's WebSocket stream for the Stage A 50 (bars) and the Stage B 10
(bars + quotes + trades). Minute bars land in `bars_minute_hot` and in an in-memory ring buffer the
feature code reads from.

**R-6.5.b** — The stream adapter MUST detect gaps (a missing minute for a symbol that traded) and
backfill from REST within 5 seconds. A feature computed over a window containing a silently missing bar
is wrong in a way that is invisible.

**R-6.5.c** — On WebSocket disconnect the engine MUST attempt reconnect with backoff, and if the
stream is not restored within `stream_outage_halt_seconds` (default **30s**) while positions are open,
it MUST transition to `HALTED` and notify the operator. Trading blind is worse than not trading.

#### 6.5.4 Nightly archival

At 17:00 ET, `bars_minute_hot` for the day is written to a Parquet partition, the hash is recorded, the
partition is read back and verified, and only then is the hot table truncated. Verify before delete,
always.

### 6.6 Data contracts

**R-6.6.a** — Every ingested record passes a Pydantic model at the boundary. Rejects go to
`ingest_rejects` with the raw payload and the validation error; they are not dropped. A rising reject
rate is a leading indicator of a vendor change.

**R-6.6.b** — Bar sanity invariants, enforced at ingest: `low <= open <= high`, `low <= close <= high`,
`volume >= 0`, `trade_count >= 0`, `ts` aligned to the bar grid, no duplicate `(symbol, ts)`. Violations
are rejects, not warnings.

### 6.7 The data quality gate

Runs after nightly ingest. Writes a `data_quality_runs` row with per-check results.

| Check | Threshold | Severity |
|---|---|---|
| Daily bars present for ≥99.5% of snapshot universe | < 99.5% | **BLOCK** |
| Minute bar coverage for top-1500 ≥ 99.0% of expected bars | < 99.0% | **BLOCK** |
| Zero duplicate `(symbol, ts)` | any | **BLOCK** |
| Bar invariants (R-6.6.b) all pass | any failure | **BLOCK** |
| Calendar has today and next 30 sessions | missing | **BLOCK** |
| Corporate actions ingested for prior session | none when expected | WARN |
| Median absolute daily return across universe within [0.2%, 5%] | outside | WARN |
| Count of symbols with >50% single-day move | > 2× trailing-30d mean | WARN |
| Ingest reject rate | > 0.5% of records | WARN |
| Prior day's close in `bars_daily` matches broker's last price ±1 tick, 20-symbol sample | mismatch | **BLOCK** |

**R-6.7.a** — A **BLOCK** result MUST prevent the engine from leaving `WARMUP` and MUST notify the
operator. Atlas does not trade on data it cannot vouch for. There is no override flag; fixing the data
is the only path forward.

**R-6.7.b** — Gate results MUST be persisted and surfaced on the frontend's system-health panel with
the timestamp of the last successful run.

### 6.8 Retention

| Data | Retention |
|---|---|
| Daily bars | forever |
| Minute bars (Parquet) | forever (compressed; ~2–4 GB/year for the archived universe) |
| `bars_minute_hot` | current day |
| Quotes/trades raw stream | 30 days of recorded sessions for fill-model calibration (§8.3.4), sampled |
| Orders, fills, positions, PnL | forever |
| `audit_log` | forever |
| Model artifacts | forever for promoted models; 90 days for rejected candidates |
| Backtest runs | forever for gated runs; 30 days for ad-hoc |

---

## 7. Stage A — deterministic narrowing, ~8,000 → 50

### 7.1 What Stage A is for

Stage A is **not** a prediction. It is a set of tradeability constraints plus a coarse attention filter.
The distinction matters and is the core design claim of the pipeline:

> Rules fail as alpha generators. They do not fail as filters. "Do not trade anything with a 20bps
> spread" is not a forecast — it is a statement about what this account can execute without giving
> the edge back to the market.

Making one model learn liquidity constraints and alpha from the same objective is how these projects
die: the model spends its capacity learning that illiquid names have noisy returns, which we already
know and can state in one line of code, and has none left for the part that is actually hard.

**R-7.1.a** — Stage A MUST be fully deterministic, side-effect free, and expressible as pure predicates
over a feature row. Given the same inputs it MUST produce the same 50 symbols in the same order,
byte-for-byte. No randomness, no wall-clock reads, no network calls inside the predicates.

**R-7.1.b** — Stage A MUST record, for every symbol in the starting universe, which predicate rejected
it first (`scan_candidates.rejected_by`). A scanner that outputs only its winners cannot be debugged
and cannot be audited. This table is also what the frontend shows the operator when they ask "why
isn't NVDA in here today".

### 7.2 Inputs

Computed at 08:45 ET from data available at that moment:

| Input | Source | Notes |
|---|---|---|
| Prior 60 daily bars | `bars_daily` | adjusted as-of today |
| Prior 20 sessions' minute bars | Parquet / hot | for intraday volatility + volume profile |
| Pre-market bars 04:00–08:45 today | stream / REST | gap and pre-market volume |
| Latest NBBO snapshot | `MarketDataPort.snapshots()` | spread estimate |
| Asset master as of today | `universe_snapshots` | tradeable, shortable, easy-to-borrow |
| Corporate actions with `knowledge_at <= now` | `corporate_actions` | pending splits, ex-div today |
| Halt status | `ReferenceDataPort` | |

### 7.3 The filters, in order

Applied as a pipeline. Order matters for cost (cheapest and most eliminating first) and for the
`rejected_by` attribution. All thresholds live in config (§11.2) and all defaults below are starting
points to be tuned in Phase 2 — but **tuned against the tradeability objective, not against returns**.
Tuning Stage A thresholds to maximize backtested PnL turns it into an alpha model fit on 8,000 names
and reintroduces exactly the overfitting the two-stage split exists to avoid.

**Tier 1 — eligibility (hard, never tuned)**

| # | Rule | Default |
|---|---|---|
| A1 | `asset.tradable` is true at Alpaca | — |
| A2 | Asset class is US equity; type is common stock or ETF | — |
| A3 | Not currently halted; no halt in the prior session | — |
| A4 | Listed ≥ `min_listing_days` (no IPOs without history) | 60 days |
| A5 | Not in the manual exclusion list (`symbol_exclusions`) | — |
| A6 | No pending corporate action with ex-date today or tomorrow (split, reverse split, merger, spin-off) | — |
| A7 | If the candidate direction is short: `shortable` and `easy_to_borrow` | — |

**Tier 2 — liquidity (hard, tuned only within a narrow band)**

| # | Rule | Default |
|---|---|---|
| A8 | 20-day median dollar volume ≥ `min_adv_usd` | $20,000,000 |
| A9 | Yesterday's dollar volume ≥ `min_prev_dollar_volume` | $5,000,000 |
| A10 | Price within `[min_price, max_price]` | [$5.00, $1,000.00] |
| A11 | Median quoted spread over the last 20 sessions ≤ `max_spread_bps` | 15 bps |
| A12 | Current snapshot spread ≤ `max_spread_bps_now` | 25 bps |
| A13 | 20-day median minute-bar trade count ≥ `min_trades_per_minute` | 30 |
| A14 | Our intended position ≤ `max_participation_pct` of 20-day median *minute* volume | 1.0% |

A14 is the rule that keeps Atlas honest about its own size. It is evaluated against the authorized
capital for the day (§13.1), so the tradeable universe shrinks as the account grows. That is correct
behaviour, not a bug.

**Tier 3 — volatility (need enough movement to pay for the spread)**

| # | Rule | Default |
|---|---|---|
| A15 | 14-day ATR as % of price ≥ `min_atr_pct` | 1.5% |
| A16 | 14-day ATR as % of price ≤ `max_atr_pct` | 15% |
| A17 | Expected move must clear costs: `ATR% × expected_capture ≥ round_trip_cost_bps × cost_multiple` | `expected_capture` 0.25, `cost_multiple` 3.0 |

A17 is the economic core of Stage A and MUST be implemented explicitly rather than folded into A15.
It states: *we only look at names where a plausible fraction of the day's range covers our costs
several times over.* §8.3 defines `round_trip_cost_bps`.

**Tier 4 — attention (this is the only ranking-ish part)**

| # | Rule | Default |
|---|---|---|
| A18 | Relative volume: pre-market volume ÷ 20-day median pre-market volume ≥ `min_rvol` | 1.5× |
| A19 | Absolute pre-market dollar volume ≥ `min_premarket_dollar_volume` | $500,000 |
| A20 | Overnight gap `abs(premarket_last / prev_close − 1)` ≥ `min_gap_pct` | 1.0% |

**R-7.3.a** — A18–A20 are an **OR-of-thresholds within an AND of eligibility**: a symbol qualifies for
attention if it passes A19 and (A18 **or** A20). Tiers 1–3 are all-AND and MUST NOT be relaxed by the
attention tier.

### 7.4 Selecting the 50

After filtering, typically 80–400 symbols survive on a normal day. Rank them by a transparent,
documented composite and take the top 50.

```
stage_a_score =
      0.40 × z(log(relative_volume))
    + 0.25 × z(log(premarket_dollar_volume))
    + 0.20 × z(abs(gap_pct) clipped to [0, 0.15])
    + 0.15 × z(atr_pct clipped to [min_atr_pct, max_atr_pct])
```

where `z()` is a cross-sectional z-score computed over the surviving set on that date, winsorized at
±3σ.

**R-7.4.a** — `stage_a_score` MUST be persisted per candidate. It is the **mandatory ML baseline** in
§9.7: if the LightGBM ranker cannot beat "just take the top 10 by `stage_a_score`", the ML layer is not
earning its complexity and MUST NOT be promoted.

**R-7.4.b** — Weights MUST live in config and be versioned with the scan run. They MUST NOT be fit by
optimizing backtested returns (see §7.3 preamble). If a weight change is proposed, it needs an ADR
explaining the *tradeability* or *attention* rationale.

**R-7.4.c** — If fewer than `min_candidates` (default **15**) symbols survive Tiers 1–3, Atlas MUST NOT
relax thresholds to fill the list. It reports a thin day, and the engine MUST be permitted to trade
nothing. A day with no trades is a normal outcome, and the notification copy (§13.4) treats it as such.

**R-7.4.d** — If more than `max_candidates_hard` (default **400**) survive, that is a signal that a
filter is mis-specified or the market is in an unusual regime. The scan proceeds but flags
`regime_warning` on the run, which raises the Stage C threshold (§9.6) and notifies the operator.

**R-7.4.e** — Sector concentration guard: no more than `max_per_sector` (default **12**) of the 50 may
share a sector, taking the highest-scoring ones. Fifty names that are all the same trade is one trade.

### 7.5 Outputs

`scan_runs`: id, `as_of`, config version, feed, universe size, counts surviving each tier, duration,
`regime_warning`, git SHA of the scanner.

`scan_candidates`: run id, symbol, rank, `stage_a_score`, every input feature value, `passed`,
`rejected_by` (first failing rule ID, null if passed), candidate direction hint (long/short/both from
gap sign and trend).

**R-7.5.a** — A scan run MUST complete within `scan_deadline_seconds` (default **180s**) for the full
universe. If it exceeds the deadline it MUST abort and notify, not silently deliver stale results.
Target: well under 60s, achieved by doing the daily-bar work as a single set-based SQL query rather
than 8,000 round trips.

### 7.6 Building and validating Stage A

Phase 2 acceptance (§20.4) requires:

- A backtest of Stage A alone over ≥ 2 years, reporting: daily survivor count distribution, turnover
  of the 50 (how many carry over day to day), and realized next-day range vs. the filtered-out
  population.
- Evidence that the Tier 2 liquidity filters are *binding*: the distribution of realized slippage for
  names just above vs. just below each threshold (§8.3.4).
- Twenty days spot-checked against the Alpaca MCP (§19.1) — pull the snapshot for ten candidates and
  ten rejects and confirm the scanner's view matches the market's, with the findings written to
  `docs/research/`.

---

## 8. Backtester and simulation

### 8.1 Standard of evidence

The backtester's job is to be **believed by a skeptic**, not to produce a good number. Every design
choice below trades optimism for credibility.

**R-8.1.a** — The backtester MUST be pessimistic at every point where the true answer is unknown:
worst-case fill within the bar, costs rounded up, latency rounded up, partial fills assumed when
volume is tight. If an assumption could go either way, take the one that makes the strategy look worse.

**R-8.1.b** — Any backtest whose results are used in a promotion decision MUST record: git SHA,
config hash, feature set version, model id, data partition hashes, random seeds, wall-clock, and the
exact date range. Reproducing it from the manifest MUST yield identical results, verified by a
golden-run test in CI (§18.7).

### 8.2 It is the engine, not a copy of the engine

**R-8.2.a** — The backtester MUST execute `services/engine/` decision code unchanged, driven by
simulated implementations of `ClockPort`, `MarketDataPort`, and `BrokerPort` (R-4.3.b). It MUST NOT
contain a reimplementation of the entry/exit logic, the risk governor, or feature computation.

This is worth restating because it is the most commonly violated rule of its kind: if you find yourself
writing `if signal > threshold: pnl += ...` in the backtester, stop. You have built a second system
that will drift from the first.

**R-8.2.b** — The simulated broker MUST enforce the same constraints as the real one: buying power,
shortability, order-type validity, tick size, minimum quantity, duplicate `client_order_id` rejection,
and the same rejection taxonomy (§10.5).

### 8.3 Cost and fill model

#### 8.3.1 Explicit costs

| Component | 2026 default | Notes |
|---|---|---|
| Commission | $0.00 | Alpaca equities |
| SEC Section 31 fee | `sec_fee_rate` × sell notional | **sells only**; rate changes annually — config, verified at ingest |
| FINRA TAF | `taf_per_share` × shares sold, capped `taf_cap` | **sells only** |
| Borrow cost | `borrow_bps_annual` × notional × holding days / 360 | shorts; intraday → usually ~0 but MUST NOT be hardcoded to 0 |
| Regulatory/exchange other | `misc_fee_bps` | conservatism buffer, default 0.1 bps |

**R-8.3.a** — Fee rates MUST live in `libs/atlas_core/costs/` as dated config
(`effective_from` → rate), not as constants, and the rate applicable to the backtest date MUST be used.
Every rate MUST cite its source in `docs/SOURCES.md` with the date it was checked.

#### 8.3.2 Spread

**R-8.3.b** — Every simulated fill MUST cross the spread. Marketable orders fill at the far touch plus
slippage; they never fill at the mid. Modeling fills at the mid is the single most common way an
intraday backtest manufactures returns that do not exist.

Spread at simulation time comes from, in order of preference:
1. Recorded NBBO from the session, if the day is in the 30-day recorded window (§6.8).
2. The symbol-day median spread from the quote sample.
3. A model: `spread_bps = f(price, ADV, minute volume, time of day)`, fit in Phase 3 from recorded
   quotes and stored in `libs/atlas_core/costs/spread_model.py`. Intraday U-shape (wide at open, tight
   midday, widening into the close) MUST be represented; a flat spread constant is not acceptable.

#### 8.3.3 Slippage and participation

```
fill_price = far_touch ± slippage
slippage_bps = base_slippage_bps
             + impact_coefficient × sqrt(order_shares / bar_volume)
             + urgency_premium (if the order is a force-flatten, §12.4)
```

**R-8.3.c** — An order MUST NOT fill for more than `max_bar_participation` (default **10%**) of that
bar's volume. The remainder rests and attempts the next bar, or is cancelled per the order's TIF.
Assuming unlimited fill at the touch is unlimited free money.

**R-8.3.d** — A simulated marketable order MUST NOT fill in the same bar the signal was computed from
(R-6.4.g). Signal from bar *t* → order submitted at *t+1* open → fill during *t+1* subject to the
latency model.

#### 8.3.4 Calibration

**R-8.3.e** — The slippage and spread models MUST be **calibrated against Atlas's own paper fills**
before Phase 8, and recalibrated monthly thereafter. `fill_quality` records, for every real fill:
the NBBO at decision time, at submission, and at fill; the modeled expected fill; and the realized
difference. A persistent bias where reality is worse than the model is a promotion blocker (§20.9 G4).

#### 8.3.5 Latency

**R-8.3.f** — The simulator MUST apply a latency budget between decision and order arrival, default
**250ms**, with the p95 measured from paper trading used once available. During that window the market
moves; the simulator MUST advance the price series accordingly rather than freezing it.

### 8.4 Mechanics

- **Event loop**: minute bars, in timestamp order, across all symbols simultaneously. Within a
  timestamp, process order fills before new decisions.
- **No survivorship**: universe per day from `universe_snapshots` (R-6.4.b).
- **Halts**: a halted symbol cannot be traded; positions in it cannot be exited. The simulator MUST
  model this, including gap-on-resume.
- **Corporate actions**: positions held across an ex-date do not occur (intraday only), but a split
  mid-backtest changes the share count for feature purposes; adjustment is as-of (R-6.4.d).
- **Capital**: start with the configured account size; positions consume buying power; the risk
  governor's limits apply exactly as in live.

**R-8.4.a** — The backtester MUST support **walk-forward** operation: train on window *W*, test on the
immediately following out-of-sample window, roll. A single train/test split is not acceptable evidence
for promotion (§9.7).

### 8.5 Reported metrics

Per run, written to `backtest_runs` and a Parquet blotter:

- Net PnL, gross PnL, total costs broken out by component (this ratio is the headline: if costs are
  >50% of gross, the strategy is a fee generator).
- Sharpe (annualized, on daily returns), Sortino, **Deflated Sharpe Ratio** (§9.7), max drawdown,
  Calmar, daily win rate, per-trade win rate, average win / average loss, profit factor.
- Trade count, median holding period, turnover, average participation rate.
- Exposure: average and max gross/net, time in market.
- Distribution: per-day PnL histogram, worst 5 days, longest losing streak.
- Attribution: PnL by symbol, by sector, by hour of day, by entry reason, by exit reason.
- **Capacity**: the same run re-simulated at 2×, 5×, 10× capital, to show where the edge dies.

**R-8.5.a** — Every backtest report MUST show net-of-cost results as the primary number. A gross-PnL
headline with costs in a footnote is misleading and is not permitted in any artifact the operator
reads.

**R-8.5.b** — Every backtest MUST report the number of distinct configurations tried to reach it
(`trials_count`, tracked in `research_trials`). This feeds the Deflated Sharpe calculation. Trying 200
configurations and reporting the best one without this correction is the standard way quantitative
projects fool themselves.

---

## 9. The machine learning layer

### 9.0 Structure of the pipeline

```
  ~8,000 symbols
        │
        │  Stage A — deterministic rules (§7)
        ▼
       50 candidates ────────────────► stage_a_score (baseline, R-7.4.a)
        │
        │  Stage B — LightGBM LambdaRank (§9.5)
        ▼
       10 selected
        │
        │  Stage C — meta-label gate (§9.6): binary classifier,
        │            "given we would trade this, will it work?"
        ▼
    trade / don't trade  ─────► size (§12.2) ─────► risk governor (§12) ─────► broker
```

Three models is not three times the complexity when each has a single, narrow job. One model trying to
do all three learns liquidity, ranking, and timing from one objective and does none of them well.

### 9.1 How standard ML silently fails on financial data

This table is the reason the ML section is long. Every row is a way to produce an excellent backtest
and lose money. Each has a mandatory mitigation and, where marked, a test in `tests/leakage/`.

| # | Standard practice | Why it fails here | **What Atlas does** | Test |
|---|---|---|---|---|
| L1 | `KFold` / random shuffle split | Labels from overlapping windows put near-identical samples in train and test; serial correlation does the rest. Test scores are fantasy. | **Purged walk-forward CV with embargo** (§9.4.2). Random splits are banned in code review. | `test_cv_is_time_ordered` |
| L2 | Train/test split ignoring label horizon | A label at *t* depends on prices up to *t+h*. A test sample starting at *t+1* overlaps the train label's future. | Purge all training samples whose label window intersects the test window; embargo `h` bars after. | `test_purge_removes_overlap` |
| L3 | Scaler / imputer fit on the full dataset | Test-set statistics leak into training. | Fit every transform **inside the fold**, persisted in the pipeline object. Fitting on all data is a lint failure. | `test_no_global_fit` |
| L4 | Universe = today's listed symbols | Survivorship bias. Companies that went to zero are missing. | PIT universe snapshots including delistings (R-6.4.b). | `test_universe_is_as_of` |
| L5 | Back-adjusted price series | A split today rewrites the past; yesterday's model saw different data. | Raw storage, as-of adjustment at read (R-6.4.d). | `test_adjustment_is_as_of` |
| L6 | Feature and entry on the same bar | You cannot trade on a close you only know at the close. | Feature at *t*, order at *t+1* open (R-8.3.d, R-6.4.g). | `test_bar_alignment` |
| L7 | Centered rolling windows, `bfill`, `shift(-n)` | Direct future leakage, often accidental via pandas defaults. | Causal windows only; AST check bans the patterns (R-6.4.f). | `test_no_future_ops` |
| L8 | Accuracy / AUC as the objective | 55% accuracy on a payoff that loses 2 when wrong and wins 1 when right is a losing system. | Objective and gates are **expected net PnL after costs** and precision@k (§9.7). | — |
| L9 | No cost model in labels | The label says "price rose 40bps"; the spread was 30bps and you paid it twice. | Costs are inside the barriers (R-9.3.b). | `test_labels_include_costs` |
| L10 | IID sample weighting | Overlapping labels mean samples are not independent; concurrent events are over-counted. | Sample weights by **average uniqueness** and return attribution (§9.4.3). | `test_sample_weights` |
| L11 | Reporting the best of N configurations | Multiple-testing. With 200 trials, a Sharpe of 2 is expected from noise. | Trial counting + **Deflated Sharpe Ratio** (§9.7 G3). | `test_trials_counted` |
| L12 | Fundamentals/estimates at their final value | Restated data was not known at the time. | `knowledge_at` filtering (R-6.4.a). Currently no fundamentals; the rule pre-exists the need. | `test_knowledge_time_filter` |
| L13 | Training on names Stage A would reject | The model learns from trades the system could never place. | Stage A predicates applied during label generation (R-4.4.b). | `test_labels_respect_stage_a` |
| L14 | Ignoring halts and missing bars | Gap-through fills that were impossible. | Halt state in the simulator (§8.4); gap detection at ingest (R-6.5.b). | `test_halted_not_fillable` |
| L15 | Feature code duplicated between research and live | Train/serve skew: the model sees different inputs in production. | Single shared module + parity test (R-4.4.a, R-4.4.c). | `test_feature_parity` |
| L16 | One long backtest, one number | Regime luck. 2023–2024 was kind to momentum. | Walk-forward across ≥3 regimes; per-fold and per-year reporting (§9.7 G5). | — |
| L17 | Tuning Stage A thresholds on PnL | Turns the filter into an 8,000-name alpha fit and defeats the two-stage split. | Stage A tuned on tradeability only (R-7.4.b). | — |

**R-9.1.a** — `tests/leakage/` MUST be a first-class suite running on every commit, and a failure there
MUST block merge. These tests protect against a class of bug that produces *better* results when
broken, which means nothing else will catch it.

### 9.2 Feature store

#### 9.2.1 Principles

- Features are **pure functions** of `(symbol, as_of, bar history)`. No hidden state, no globals.
- Each feature has a name, version, dtype, causal window length, and a docstring saying what it
  measures and why it might matter.
- The set of features used by a model is pinned by `feature_set_version` and stored with the artifact.

**R-9.2.a** — A feature MUST NOT be added without a stated hypothesis. "Try everything and let the
model sort it out" with 400 features on a few hundred thousand overlapping samples is how you fit
noise. Target **40–80** features, reviewed for redundancy.

#### 9.2.2 Feature families

| Family | Examples | Horizon |
|---|---|---|
| Trend / momentum | returns over 1/5/15/30/60min and 1/5/20d; distance from VWAP; EMA slopes; position in day's range | intraday + daily |
| Volatility | realized vol over multiple windows; ATR%; Parkinson/Garman-Klass estimators; vol-of-vol; ratio of intraday to overnight vol | intraday + daily |
| Volume | relative volume vs. time-of-day profile; volume acceleration; dollar volume; trade count; average trade size | intraday |
| Microstructure | quoted spread (bps), effective spread, quote imbalance, trade sign imbalance (tick rule), Amihud illiquidity | intraday |
| Gap / open | overnight gap %, pre-market range, pre-market volume vs. profile, gap fill progress, opening-range position and width | daily open |
| Cross-sectional | rank of each of the above within the day's Stage A 50; sector-relative return; beta-adjusted return vs. SPY | daily |
| Regime | SPY/QQQ trend and realized vol, VIX level and change, market breadth (advance/decline of the universe), time of day, day of week, days to month end | market-wide |
| Positional | current unrealized PnL, time in trade, distance to stop/target (Stage C only) | live |

**R-9.2.b** — Cross-sectional features MUST be computed over the Stage A survivor set for that date and
MUST be rank- or z-based, so the feature distribution is stable across regimes. Raw levels drift;
cross-sectional ranks do not.

**R-9.2.c** — Time-of-day MUST be an explicit feature. Intraday dynamics at 09:45 and at 14:30 are
different processes, and a model without this feature will average them into mush.

#### 9.2.3 Stationarity

**R-9.2.d** — Features MUST be stationary or made stationary. Raw price MUST NOT be a feature.
Returns, ratios, z-scores, and ranks are acceptable. Fractional differentiation MAY be used where a
long memory is genuinely wanted; if used, the differentiation order and the ADF test result MUST be
recorded with the feature.

#### 9.2.4 Parity (the rule that matters most)

**R-9.2.e** — `tests/leakage/test_feature_parity.py` MUST, for ≥200 fixed `(symbol, timestamp)` pairs
spanning ≥6 distinct dates including a half-day and a high-volatility day:

1. Compute every feature through the **training path** (Parquet → DuckDB → pandas batch).
2. Compute every feature through the **live path** (ring buffer → incremental update).
3. Assert equality to within 1e-12, reporting per-feature max deviation on failure.

This test failing means the model in production is seeing different numbers than the model in training.
It MUST be treated as a P0.

### 9.3 Labelling: triple barrier

For each candidate event (a symbol on a date at a candidate entry time that Stage A passed), define
three barriers and label by which is touched first.

```
entry at price P0, side s ∈ {+1 long, −1 short}, at time t0
  upper barrier:    P0 × (1 + s × pt_mult × σ_t0)
  lower barrier:    P0 × (1 − s × sl_mult × σ_t0)
  vertical barrier: t0 + holding_horizon, or force-flatten time, whichever is first

label y = +1  if the profit barrier is touched first
        = −1  if the stop barrier is touched first
        =  0  if the vertical barrier is reached first  (or sign of the return, see R-9.3.c)
```

**R-9.3.a** — Barriers MUST be **volatility-scaled**, not fixed percentages. `σ_t0` is the trailing
realized volatility of returns over `vol_window` (default 60 minutes), estimated causally.
A fixed 1% target means something different for a 1%-ATR stock and a 12%-ATR stock, and a model trained
on fixed barriers learns volatility, not direction.

**R-9.3.b** — Barriers MUST be **cost-adjusted**: the profit barrier is raised and the stop lowered by
the modelled round-trip cost (§8.3) so that `y = +1` means "profitable after costs", not "the price
moved". This single choice removes an entire category of strategy that looks profitable and is not.

**R-9.3.c** — Vertical-barrier events MUST be labelled by the **cost-adjusted sign of the realized
return**, with a dead zone: if `|net return| < cost_dead_zone` the sample is labelled 0 and excluded
from the Stage C binary target while still contributing to the Stage B ranking target. Discarding them
entirely biases toward trending samples.

**R-9.3.d** — The path within the barrier window MUST be evaluated on **minute bars at minimum**, using
the bar high/low, and MUST assume that if both barriers are touched within the same bar, the **stop**
was hit first. Assuming the favourable touch first is a systematic overstatement of the strategy.

**R-9.3.e** — The vertical barrier MUST never extend past the session's force-flatten time (§12.4).
Atlas cannot hold overnight, so a label that assumes it could is unrealizable.

Defaults: `pt_mult` 2.0, `sl_mult` 1.0, `holding_horizon` 120 minutes, `vol_window` 60 minutes,
`cost_dead_zone` 5 bps. These are Phase 4 tuning targets, tuned on the training folds only.

### 9.4 Sampling, weighting, validation

#### 9.4.1 Concurrency

**R-9.4.a** — Label concurrency MUST be computed: for each bar, the number of open label windows
spanning it. This drives both sample weights (§9.4.3) and the honest count of *effective* independent
samples, which is far smaller than the row count and is what determines how much model capacity is
justified.

#### 9.4.2 Purged walk-forward CV with embargo

```
 |──────── train ────────|‖purge‖ |─ test ─| ‖embargo‖ |──── unused ────|
 |────────────── train ──────────────|‖purge‖ |─ test ─| ‖embargo‖ |────|
                                      ... rolling forward ...
```

**R-9.4.b** — Cross-validation MUST be **purged walk-forward**:
- Train windows always precede test windows in time. No exceptions, no shuffling.
- **Purge**: drop from train any sample whose label window overlaps the test window (L2).
- **Embargo**: additionally drop train samples within `embargo_bars` after the test window
  (default = 1 trading day), to defeat leakage via serial correlation of features.
- Expanding or rolling train windows both acceptable; the choice is recorded, and results from both
  SHOULD be reported since a large divergence signals regime dependence.

**R-9.4.c** — `sklearn.model_selection.KFold`, `StratifiedKFold`, `train_test_split`, and
`cross_val_score` MUST NOT appear anywhere in `services/worker/training/`. CI greps for them.
Combinatorial Purged CV MAY be used additionally to estimate the distribution of backtest outcomes.

#### 9.4.3 Sample weights

**R-9.4.d** — Training samples MUST be weighted by the product of:
- **Average uniqueness**: the inverse of mean concurrency over the sample's label window. Overlapping
  samples carry less information than their count suggests.
- **Return attribution**: absolute cost-adjusted return over the label window, so samples that mattered
  economically dominate samples that did not.
- Optionally **time decay**: linear decay giving older samples lower weight, decay floor in config.

#### 9.4.4 Class balance

Expect roughly balanced ±1 with `pt_mult`/`sl_mult` as configured; check and report it. Use
`scale_pos_weight` if skew exceeds 60/40, but **never** SMOTE or any synthetic oversampling —
interpolating between financial time-series samples produces observations that could not have occurred
and leaks across the time boundary.

### 9.5 Stage B — the ranker, 50 → 10

**Task.** Learning-to-rank within a day-group: given the 50 candidates for a date, order them by
expected cost-adjusted risk-adjusted return over the holding horizon.

**Model.** LightGBM `LambdaRank` with `group` = (date), or `regression` on the forward cost-adjusted
return with cross-sectional ranking applied afterward. Build both; the promotion gates decide.

**R-9.5.a** — Stage B MUST be trained **cross-sectionally within the day**, not pooled across time as
independent rows. The question is "which of these 50, today" and not "is this symbol good in the
absolute". Cross-sectional framing is also naturally robust to market-wide moves that a pooled model
would learn as alpha.

**R-9.5.b** — The label for Stage B is the **rank of the cost-adjusted triple-barrier return** among
that day's candidates, not the raw return. Raw returns are dominated by whichever day was volatile.

**R-9.5.c** — Hyperparameters MUST be constrained toward simplicity, tuned only on training folds:
`num_leaves` ≤ 63, `max_depth` ≤ 7, `min_data_in_leaf` ≥ 100 (scaled to effective sample count from
§9.4.1, not row count), `feature_fraction` ≤ 0.8, `bagging_fraction` ≤ 0.8, L1/L2 regularization
non-zero, `n_estimators` chosen by early stopping on the fold's validation slice. A model with more
leaves than effective independent samples per leaf is memorizing.

**R-9.5.d** — Output MUST be the full ranked 50 with scores, not just the top 10. The tail is needed
for evaluation (precision@k across k), for the frontend's explanation view, and for diagnosing whether
the model is confidently wrong or merely indifferent.

**R-9.5.e** — Feature importance (gain **and** SHAP on a sample) MUST be computed and stored with each
model. A model whose top feature is something that should not matter is a data bug, and this is how you
find it.

### 9.6 Stage C — the meta-label execution gate

**Task.** Binary classification: given that Stage B selected this name and an entry trigger has fired,
**should we actually take this trade right now?** Output is a probability; the trade is taken only if
it clears a threshold.

This is López de Prado's meta-labelling applied at execution time, and it is where most of the
practical value tends to sit: the primary model decides *what*, the secondary decides *whether*, and
the secondary can use information the primary did not have — current spread, current volume,
where the market has moved since the open, how the last few minutes have behaved.

**R-9.6.a** — Stage C MUST be trained on the **outcomes of trades Stage B would have taken**, not on
the full candidate set. Its training distribution is conditional on Stage B's selection, and mixing in
non-selected names teaches it the wrong prior.

**R-9.6.b** — Stage C's objective is **precision**, explicitly. Recall is cheap: there are always more
candidates tomorrow. The cost of a bad trade is money; the cost of a skipped good trade is opportunity.
The threshold is tuned to maximize expected net PnL per unit of risk, not F1.

**R-9.6.c** — Stage C's output probability MUST also drive **position sizing**, via a monotone map
from calibrated probability to a fraction of the maximum position size (§12.2). Probabilities MUST be
calibrated (isotonic or Platt, fit on training folds only) and calibration MUST be reported as a
reliability diagram in the model card. An uncalibrated probability used for sizing is a random number
with a decimal point.

**R-9.6.d** — If Stage C's gate rejects every candidate on a given day, Atlas trades nothing that day.
This MUST be treated as normal (R-7.4.c) and MUST NOT trigger a fallback path that trades anyway.

**R-9.6.e** — The Stage C threshold MUST be raised by `regime_warning_threshold_bump` (default +0.05)
when the scan flagged `regime_warning` (R-7.4.d), and MUST be raised while the daily loss approaches
the limit (R-12.2.f) — trade more selectively as conditions degrade.

### 9.7 Promotion gates

A trained model is a **candidate**. It becomes **promoted** — eligible for use by the engine — only by
passing every gate below, evaluated on out-of-sample walk-forward results.

**R-9.7.a** — Promotion gates MUST be enforced **in code**, in `services/worker/training/promotion.py`,
returning a structured pass/fail per gate that is persisted to `model_promotions`. There MUST be no
override flag, no `--force`, and no environment variable that skips a gate. If a gate is wrong, change
the gate in a reviewed commit with an ADR — do not build a bypass.

| Gate | Requirement | Rationale |
|---|---|---|
| **G1 · Beats the no-ML baseline** | Net-of-cost PnL per unit risk ≥ **1.20×** that of taking the top 10 by `stage_a_score` (R-7.4.a), on every walk-forward fold in aggregate and in ≥ 70% of individual folds | If ML cannot beat a weighted z-score, it is not earning its complexity, its retraining burden, or its opacity |
| **G2 · Beats random selection** | Outperforms "random 10 of the 50" at p < 0.01 over ≥ 1,000 bootstrap resamples | Establishes the selection has content at all |
| **G3 · Deflated Sharpe** | **DSR > 0.95** using `trials_count` from `research_trials` (R-8.5.b), OOS only | Corrects for the multiple-testing that makes the best of N configurations look skilled |
| **G4 · Cost robustness** | Remains profitable with costs at **1.5×** the modeled level | The cost model is the least certain input; the edge must not live inside its error bars |
| **G5 · Regime stability** | Positive net PnL in ≥ **70%** of walk-forward folds; no single fold contributes > **40%** of total PnL; positive in at least one high-vol and one low-vol regime window | Rejects models that made all their money in one lucky period |
| **G6 · Drawdown** | OOS max drawdown ≤ `max_backtest_drawdown_pct` (default **15%**) and ≤ 1.5× the baseline's | A strategy the operator would turn off during its normal drawdown is not deployable |
| **G7 · Sample sufficiency** | ≥ **1,000** effective independent samples (§9.4.1) in training; ≥ **250** OOS trades | Prevents promoting a model fit on a handful of overlapping events |
| **G8 · Capacity** | Edge survives at 2× intended capital; documented at 5× and 10× (§8.5) | Establishes headroom and where the strategy dies |
| **G9 · Calibration** | Stage C reliability: expected calibration error ≤ **0.05**; monotone probability-to-outcome relationship | Required for R-9.6.c sizing to mean anything |
| **G10 · Parity & provenance** | `test_feature_parity` passes; feed matches (R-6.2.b); manifest reproduces the run bit-for-bit (R-8.1.b) | The artifact is what we think it is |
| **G11 · Leakage suite** | All of `tests/leakage/` green on the exact commit that trained the model | Everything above is meaningless if L1–L17 are in play |

**R-9.7.b** — **G1 is the honest-failure gate.** If the ML layer cannot clear it after a genuine effort,
the correct outcome is to ship Stage A + Stage C (or Stage A alone) and delete the ranker. Record it in
an ADR. Shipping a model that does not beat its baseline because it was expensive to build is how a
system becomes unmaintainable and unprofitable simultaneously.

**R-9.7.c** — Gate results MUST be rendered as a **model card** (`docs/research/models/<model_id>.md`)
with metrics, feature importance, calibration plot, per-fold results, and the failure modes observed.
Promotion without a model card is not permitted.

### 9.8 Model registry, deployment, rollback

**R-9.8.a** — Models are immutable artifacts in Supabase Storage at `models/<model_id>/` containing:
`model.txt` (LightGBM native), `feature_set.json` (ordered names, dtypes, versions), `pipeline.pkl`
(fitted transforms), `manifest.json` (git SHA, data hashes, seeds, date ranges, hyperparameters,
`trials_count`), `metrics.json`, `model_card.md`. `model_id` = content hash.

**R-9.8.b** — The engine at startup MUST load the model marked `active` for its stage, verify the
artifact hash, and verify that `feature_set_version` matches the version the feature module reports.
A mismatch MUST prevent the engine leaving `WARMUP` — it MUST NOT fall back to an older model silently.

**R-9.8.c** — Model activation is an **operator action** through the API, recorded in `audit_log` with
the promotion record. It MUST NOT happen automatically at the end of a training run, even when all
gates pass. Training proposes; the operator disposes.

**R-9.8.d** — Rollback MUST be a single action that reactivates the previous model, and MUST be
possible while the engine is running, taking effect at the next scan (not mid-position).

**R-9.8.e** — A newly promoted model MUST run in **shadow mode** for ≥ 10 trading sessions before it
can be activated for live: it produces predictions that are logged and scored but not traded, alongside
the active model. The comparison is part of the activation decision.

### 9.9 Monitoring and drift

**R-9.9.a** — For every live prediction, Atlas MUST log the full feature vector, the model id, the
score, the Stage C probability, the decision, and the eventual realized outcome once the label
resolves. This is the dataset for the next retrain and the only way to answer "what did it see".

**R-9.9.b** — Drift monitoring MUST run daily: population stability index per feature against the
training distribution, and rolling realized precision@10 vs. the OOS expectation. A PSI > 0.25 on any
top-10-importance feature, or realized precision below the OOS 5th percentile for 10 consecutive
sessions, MUST notify the operator and MUST automatically raise the Stage C threshold
(`drift_threshold_bump`, default +0.05).

**R-9.9.c** — If realized net PnL over a rolling 20-session window falls below the OOS 1st percentile,
the engine MUST transition to `HALTED` and require operator review before resuming. The model has
stopped working and the system should notice before the operator's balance does.

### 9.10 Retraining

- **Cadence**: weekly candidate training on the worker; monthly considered for activation.
- **R-9.10.a** — Retraining MUST use the identical pipeline, gates, and code path as the initial
  training. There is no "quick retrain" script.
- **R-9.10.b** — Every retrain increments `trials_count`, feeding G3. Retraining until the gates pass
  is a form of overfitting and the DSR correction is what makes that visible.
- **R-9.10.c** — The training data window MUST be recorded and MUST NOT be shortened to exclude a bad
  period without an ADR justifying the regime argument.

---

## 10. Execution engine

### 10.1 The one order path

**R-10.1.a** — Exactly one module, `services/engine/execution/submit.py`, exposes exactly one
coroutine that calls `BrokerPort.submit_order`. Its name is `submit_order_through_governor`. No other
call site in the repository may invoke `BrokerPort.submit_order`, `.cancel_order`, or `.replace_order`.

**R-10.1.b** — That function's body, in order, with no branch that skips a step:

```python
async def submit_order_through_governor(intent: OrderIntent, ctx: DecisionContext) -> OrderResult:
    # 1. Load authoritative state: account, positions, working orders, today's realized PnL
    state = await store.load_risk_state(ctx.as_of)

    # 2. Authorization check — R-3.4.a. Unexpired, unrevoked, covers this symbol and notional
    grant = await store.active_grant(ctx.as_of)

    # 3. Kill-switch check — R-13.2.c. Reads BOTH in-process flag and durable halt state
    halt = await store.halt_state()

    # 4. RISK GOVERNOR — pure function, no I/O. Returns Approved(order) | Rejected(rule_id, reason)
    decision = risk.evaluate(intent, state, grant, halt, ctx.clock.now(), ctx.config)

    # 5. Persist the decision (approved or rejected) + audit_log row, ONE transaction — R-3.7.a
    await store.record_decision(decision)      # assigns client_order_id, idempotency key

    if decision.rejected:
        return OrderResult.rejected(decision)

    # 6. Submit. The ONLY call to the broker's order API in the codebase.
    return await broker.submit_order(decision.order)
```

**R-10.1.c** — There MUST be no parameter, environment variable, config key, or code path that skips
step 4. No `force`, no `bypass_risk`, no `dry_run=False` shortcut, no debugging helper. A CI check
(`tests/unit/test_single_order_path.py`) greps the AST of the whole repository for calls to the broker
order methods and fails if any exist outside `submit.py` and `adapters/`.

**R-10.1.d** — Cancels and replaces go through a parallel single path
(`cancel_order_through_governor`), because a cancel can also be dangerous — cancelling a protective
stop while a position is open is a risk event and the governor MUST evaluate it.

### 10.2 Intent → order

The engine's decision code produces an `OrderIntent`, a pure value object: symbol, side, target
notional, order type, limit price (if any), time in force, entry reason, Stage C probability,
originating `rank_run_id`, and a deterministic `intent_id`.

**R-10.2.a** — `OrderIntent` MUST be immutable and MUST carry enough provenance to reconstruct why the
order existed: which scan, which rank, which model, which score, which trigger.

### 10.3 Order lifecycle and state

```
 INTENT ─► RISK_APPROVED ─► SUBMITTED ─► ACCEPTED ─► PARTIALLY_FILLED ─► FILLED
    │            │              │            │               │
    │            ▼              ▼            ▼               ▼
    └──► RISK_REJECTED   SUBMIT_FAILED   REJECTED       CANCELLED / EXPIRED
```

**R-10.3.a** — Order state transitions MUST be persisted with `SELECT ... FOR UPDATE` on the order row
and an explicit allowed-transition table. An illegal transition MUST raise and MUST NOT be silently
coerced. Every transition writes an `order_events` row (append-only) with the broker's raw payload.

**R-10.3.b** — The broker's order stream is the **source of truth** for order state. The engine's local
state is a cache. Where they disagree, the broker wins and a reconciliation event is logged (§10.6).

### 10.4 Order construction

**R-10.4.a** — Entries MUST be **marketable limit orders**, never plain market orders. Limit price =
far touch ± `entry_limit_slippage_bps` (default 10 bps). A market order in a thin book is an
unbounded-price order, and the whole Stage A liquidity apparatus exists to make this limit tight.

**R-10.4.b** — Exits MUST also be marketable limit orders, except the force-flatten at 15:55 (§12.4),
which MAY escalate: marketable limit, then re-price twice at widening offsets, then market order at
`force_market_after_seconds` (default 60s). Escalation MUST be logged per step.

**R-10.4.c** — Every entry MUST be accompanied by a **protective stop** submitted as part of the same
bracket, or as a separate stop order submitted immediately on fill confirmation. A filled entry
without a resting stop is an unbounded-loss position and MUST raise an alert if it persists more than
`stop_placement_deadline_seconds` (default 5s).

**R-10.4.d** — Prices MUST be quantized to the symbol's tick size ($0.01 above $1.00; $0.0001 below)
and quantities to whole shares (no fractional shares — they complicate shorting and stop orders for no
benefit here).

**R-10.4.e** — Time in force MUST be `day`. Never `gtc`, never `opg`, never `cls`. An order that
survives the session is an overnight risk (§2.1).

### 10.5 Idempotency

**R-10.5.a** — Every order carries a deterministic `client_order_id` =
`sha256(strategy_version | intent_id | symbol | side | session_date | attempt)` truncated to Alpaca's
limit. Alpaca rejects duplicate `client_order_id`, which converts the dangerous case (network timeout
→ retry → two positions) into a harmless rejection.

**R-10.5.b** — On any ambiguous submission outcome (timeout, connection reset, 5xx), the engine MUST
NOT blindly retry. It MUST query the broker for the order by `client_order_id`, and only submit again
if the broker has no record. This reconciliation-before-retry loop is mandatory, and the
`attempt` counter increments only after confirmed absence.

**R-10.5.c** — The rejection taxonomy MUST be explicit and each class handled deliberately:
duplicate id (treat as success, reconcile), insufficient buying power (risk state is stale → resync,
do not retry), not shortable (mark symbol, skip for the day), symbol halted (skip, re-evaluate on
resume), rate limited (back off), malformed (bug → alert, halt that intent), unknown (halt and alert).

### 10.6 Reconciliation

**R-10.6.a** — The engine MUST reconcile local position and order state against the broker:
at startup, every `reconcile_interval_seconds` (default **60s**) during `TRADING`, on every stream
reconnect, and at session close.

**R-10.6.b** — A position discrepancy (broker shows a position Atlas does not know about, or a
different quantity) MUST immediately transition the engine to `HALTED` and notify the operator with
both views. This is not a recoverable condition to paper over; it means the engine's model of reality
is wrong while it has the ability to place orders.

**R-10.6.c** — At session close, realized PnL MUST be computed from broker fills, not from Atlas's
internal expectations, and written to `pnl_daily` with per-trade attribution. Any difference between
expected and broker-reported PnL beyond `pnl_tolerance_usd` (default $1.00) is logged as a discrepancy
and surfaced.

### 10.7 Entry and exit logic

Deliberately simple. The edge, if any, is supposed to come from selection (Stage A/B) and timing
(Stage C), not from an elaborate exit heuristic that is itself fit to the backtest.

**Entry.** For each of the 10 selected names, the engine watches for its trigger — a configurable,
versioned rule (default: price crosses the opening-range high/low in the direction of the Stage B hint,
with volume confirmation), evaluated on completed bars only (R-6.4.g). On trigger, Stage C scores it;
if the probability clears the threshold, an `OrderIntent` is produced.

**Exit.** Whichever comes first:
- Protective stop (R-10.4.c), at the same volatility-scaled distance used by the labelling (§9.3).
- Profit target at `pt_mult × σ`, matching the label.
- Time stop at `holding_horizon`, matching the label's vertical barrier.
- Force-flatten at 15:55 (§12.4).
- Kill switch.

**R-10.7.a** — Exit parameters MUST match the labelling parameters (§9.3). A model trained to predict
"hits +2σ before −1σ within 120 minutes" and traded with a trailing stop at 0.5σ is being asked a
different question than it was trained on. If exit logic changes, labels are regenerated and the model
is retrained.

**R-10.7.b** — There MUST be no averaging down, no adding to losers, no re-entry into a symbol after
a stop-out on the same day (`max_entries_per_symbol_per_day` default **1**). These are the behaviours
that convert a bounded loss into an unbounded one.

### 10.8 Failure behaviour

| Failure | Response |
|---|---|
| Broker API 5xx, sustained | Circuit breaker → `HALTED`, notify, attempt to flatten via retry with backoff |
| Order stream disconnected | Reconnect with backoff; reconcile on restore; `HALTED` after `stream_outage_halt_seconds` with positions open (R-6.5.c) |
| Market data stream stalled | Same as above — no data means no decisions, and positions must not be managed blind |
| Database unreachable | Engine cannot persist decisions → MUST NOT trade (R-3.7.a makes this automatic); flatten if positions are open, then `HALTED` |
| Engine process crash | Fly restarts; engine boots into `WINDING_DOWN` with open positions (R-4.6.c) and reconciles |
| Fly machine lost entirely | Positions have resting protective stops (R-10.4.c) and TIF=day (R-10.4.e), so worst case is a stop-out or a flat at close, never an overnight surprise |
| Clock skew detected | `HALTED`; compare against broker clock at startup and hourly, threshold 2s |

**R-10.8.a** — The protective-stop-plus-day-TIF combination (R-10.4.c, R-10.4.e) is the last line of
defence and exists precisely so that total loss of Atlas does not mean unbounded loss of capital.
It MUST NOT be weakened for any reason, including backtest results showing stops hurt performance.

---

## 11. Configuration and environments

### 11.1 Environment selection

**R-11.1.a** — `ALPACA_ENV` MUST be read at startup, MUST be exactly `paper` or `live`, and MUST have
**no default**. A missing, empty, or unrecognized value MUST raise `ConfigurationError` and exit
non-zero before: any network call, any database connection, any scheduler registration, and any log
line other than the error itself.

```python
# libs/atlas_core/config/env.py   # R-11.1.a
class AlpacaEnv(StrEnum):
    PAPER = "paper"
    LIVE = "live"

def require_alpaca_env() -> AlpacaEnv:
    raw = os.environ.get("ALPACA_ENV")
    if raw not in ("paper", "live"):
        raise ConfigurationError(
            f"ALPACA_ENV must be explicitly 'paper' or 'live', got {raw!r}. "
            "There is no default. See MASTER_SPEC §11.1."
        )
    return AlpacaEnv(raw)
```

**R-11.1.b** — The base URL, the credential names, and the database schema MUST all be derived from
`ALPACA_ENV` in one place. It MUST be impossible to have live credentials and a paper base URL, or
vice versa. A startup self-check MUST call the broker's account endpoint and assert that the returned
account's paper/live nature matches `ALPACA_ENV`, exiting if not.

**R-11.1.c** — `ALPACA_ENV=live` MUST additionally require: `ATLAS_LIVE_CONFIRMED=yes-i-mean-it`, a
`phase >= 8` marker in config, and a promoted-and-activated model. Any missing → exit.

**R-11.1.d** — Every log line, every API response header, every frontend page, and every notification
MUST carry the environment. The operator MUST never have to guess which account they are looking at.
Live mode renders in a visually distinct colour scheme (§15.3).

### 11.2 Configuration model

Settings are typed Pydantic models in `libs/atlas_core/config/`, loaded from (in precedence order):
environment variables → `config/<env>.toml` in the repo → defaults in code.

**R-11.2.a** — Every configuration value MUST have a documented type, unit, default, and range. Units
go in the name: `max_position_notional_usd`, `stream_outage_halt_seconds`, `max_spread_bps`.

**R-11.2.b** — Risk limits (§12.2) MUST NOT be settable from environment variables in live. They live
in the repository, are changed by a reviewed commit, and are hashed into `config_versions`. A risk
limit that can be widened by editing a dashboard field at 15:40 is not a risk limit.

**R-11.2.c** — The active config hash MUST be recorded on every scan run, rank run, order, and backtest,
and MUST be displayed in the UI. Changing config mid-session MUST be detected and MUST require an
explicit engine restart.

### 11.3 Key configuration groups

| Group | Examples |
|---|---|
| Environment | `ALPACA_ENV`, `ATLAS_PHASE`, `ATLAS_LIVE_CONFIRMED` |
| Broker/data | base URLs, `data_feed` (sip/iex), rate limits, `circuit_breaker_error_rate` (0.25), `circuit_breaker_window_seconds` (60) |
| Scanner | all Stage A thresholds (§7.3), `scan_deadline_seconds`, weights |
| Model | active model ids, Stage C threshold, `drift_threshold_bump`, `regime_warning_threshold_bump` |
| Risk | every limit in §12.2 — repo-only in live |
| Execution | `entry_limit_slippage_bps`, `force_market_after_seconds`, `reconcile_interval_seconds`, `max_entries_per_symbol_per_day` |
| Session | `opening_range_minutes` (15), `no_new_entries_after` (15:45), `force_flatten_at` (15:55) |
| Costs | dated fee schedule, spread model coefficients, slippage coefficients |
| Notifications | channel routing, quiet hours, rate limits, escalation |
| Kill switch | `halt_poll_interval_ms` (250), `halt_slo_seconds` (10), `drill_max_age_days` (8) |

### 11.4 Secrets

See §16.3 for the full matrix. Summary: local dev and CI get **paper keys only**; live keys exist in
exactly two Fly secret stores and nowhere else; `.env.example` contains names with empty values and a
comment pointing at §16.3; `.mcp.json` contains paper keys only (R-19.2.a).

---

## 12. The risk governor

`services/engine/risk/`. Read this section completely before writing a line in that directory.

### 12.1 Design

**R-12.1.a** — The governor MUST be a **pure function**:

```python
def evaluate(
    intent: OrderIntent,
    state: RiskState,          # account, positions, working orders, realized PnL, day-trade count
    grant: AuthorizationGrant | None,
    halt: HaltState,
    now: datetime,             # the clock is an INPUT, never read inside
    config: RiskConfig,
) -> Decision:                 # Approved(order) | Rejected(rule_id, reason, context)
    ...
```

No I/O, no `datetime.now()`, no randomness, no logging, no global state, no async. Everything it needs
is an argument. This is what makes 100% branch coverage achievable and property testing possible.

**R-12.1.b** — Rules MUST be evaluated in a fixed, documented order, and the **first** rejection is
returned with its rule ID. Deterministic attribution is required for the audit trail and for the
operator's "why didn't it trade" question.

**R-12.1.c** — The governor MUST be **fail-closed**. Any unexpected condition — a `None` where a value
was expected, a state older than `max_risk_state_age_seconds` (default 5s), an unparseable grant, an
arithmetic error — MUST produce `Rejected`, never an exception that propagates and never an approval.
The default branch of every match statement rejects.

**R-12.1.d** — The governor MUST NOT be able to *modify* an order except to **reduce** it: it may lower
quantity to fit a limit and return `Approved` with the reduced order, and it MUST record the reduction.
It MUST NEVER increase size, loosen a limit price, or change side.

### 12.2 The rules

Evaluated in this order. All limits from `RiskConfig` (R-11.2.b).

**Group 1 — global blocks (nothing gets past these)**

| ID | Rule |
|---|---|
| R-12.2.a | `halt.active` is false. If halted, reject everything except a `flatten` intent explicitly flagged as halt-originated |
| R-12.2.b | `grant` exists, `grant.granted_at <= now < grant.expires_at`, `grant.revoked_at is None` (R-3.4.a) |
| R-12.2.c | `grant.expires_at - grant.granted_at <= 24h` — re-verified here even though the DB and API also enforce it (R-3.4.b) |
| R-12.2.d | `now` is within the trading session per the calendar, and within `[session_open, no_new_entries_after]` for entries |
| R-12.2.e | `state.as_of` is no older than `max_risk_state_age_seconds` (R-12.1.c) |
| R-12.2.f | Today's realized + unrealized loss < `max_daily_loss_usd` **and** < `max_daily_loss_pct` of starting equity. Breaching this rejects all entries AND triggers `WINDING_DOWN` |
| R-12.2.g | Consecutive-loss circuit breaker: `consecutive_losing_trades < max_consecutive_losses` (default 4) |
| R-12.2.h | Config hash matches the engine's loaded config (R-11.2.c) |

**Group 2 — authorization scope**

| ID | Rule |
|---|---|
| R-12.2.i | `intent.symbol` is in the grant's authorized symbol set (the 10 from the rank run the grant covers) |
| R-12.2.j | Order notional + existing deployed notional ≤ `grant.max_capital_usd` |
| R-12.2.k | Orders placed under this grant < `grant.max_orders` (default 60) |
| R-12.2.l | `intent.side` is permitted by the grant (the operator may authorize long-only) |

**Group 3 — position and exposure limits**

| ID | Rule |
|---|---|
| R-12.2.m | Per-position notional ≤ `max_position_notional_usd` and ≤ `max_position_pct_of_equity` (default 20%) |
| R-12.2.n | Per-trade risk (entry to stop, in dollars) ≤ `max_risk_per_trade_pct` of equity (default **0.5%**) — this is what actually determines size (§12.3) |
| R-12.2.o | Open position count ≤ `max_concurrent_positions` (default 5) |
| R-12.2.p | Gross exposure ≤ `max_gross_exposure_pct` of equity (default 100% — no leverage by default) |
| R-12.2.q | Net exposure within ±`max_net_exposure_pct` (default 60%) — not all 5 positions pointing the same way |
| R-12.2.r | Sector exposure ≤ `max_sector_exposure_pct` (default 40%) |
| R-12.2.s | Sum of per-trade risk across all open positions ≤ `max_portfolio_heat_pct` (default 2%) |
| R-12.2.t | Buying power after this order ≥ `min_buying_power_buffer_usd`, computed from broker-reported buying power, not from Atlas's estimate |

**Group 4 — per-symbol and execution sanity**

| ID | Rule |
|---|---|
| R-12.2.u | Entries per symbol today < `max_entries_per_symbol_per_day` (R-10.7.b) |
| R-12.2.v | No opposing working order or position in the same symbol (no simultaneous long and short) |
| R-12.2.w | Symbol is not halted; last trade is no older than `max_quote_staleness_seconds` (default 10s) |
| R-12.2.x | Current spread ≤ `max_spread_bps_execution` — re-checked at order time, not just at scan time |
| R-12.2.y | Limit price within `price_collar_pct` (default 5%) of last trade — catches a corrupt price feed before it becomes a fill |
| R-12.2.z | Order quantity > 0, ≤ `max_order_shares`, and ≤ `max_participation_pct` of recent minute volume (A14) |
| R-12.2.aa | Order rate: orders in the last minute < `max_orders_per_minute` (default 10); in the day < `max_orders_per_day` (default 100). A runaway loop is a real failure mode |
| R-12.2.ab | Idempotency: no existing order with this `client_order_id` in a non-terminal state (R-10.5.a) |
| R-12.2.ac | If short: symbol is shortable and easy-to-borrow per current reference data |
| R-12.2.ad | Day-trade count check — **config-gated, default disabled** (R-2.4.a) |

**R-12.2.ae** — Every rejection MUST be persisted with its rule ID and the state that caused it, and
MUST be visible in the UI. A silent rejection is indistinguishable from a bug.

### 12.3 Position sizing

Sizing happens **before** the governor (in the decision code) and is then verified by it. The governor
never sizes up.

```
risk_per_share   = |entry_price − stop_price|                     # from §9.3 volatility scaling
max_shares_risk  = (equity × max_risk_per_trade_pct) / risk_per_share      # R-12.2.n
max_shares_notional = max_position_notional_usd / entry_price             # R-12.2.m
max_shares_liquidity = participation_cap × recent_minute_volume           # A14 / R-12.2.z
confidence_scalar = f(stage_c_calibrated_probability) ∈ [0.25, 1.0]       # R-9.6.c

shares = floor(min(max_shares_risk, max_shares_notional, max_shares_liquidity) × confidence_scalar)
```

**R-12.3.a** — Sizing MUST be driven by **risk to the stop**, not by a fixed dollar amount or a fixed
share count. Equal-dollar sizing across names with 1% and 12% ATR means wildly unequal risk.

**R-12.3.b** — `confidence_scalar` MUST be monotone non-decreasing in probability and MUST be bounded
below by a floor that is > 0 only above the Stage C threshold (below it, size is zero because no trade
is taken). Kelly-style sizing MAY be explored in research but MUST NOT be used live without an ADR;
full Kelly on an uncertain edge is a path to ruin.

**R-12.3.c** — If `shares` rounds to 0, no order is placed. It MUST NOT be rounded up to 1.

### 12.4 End of day

**R-12.4.a** — At `no_new_entries_after` (default **15:45 ET**) the engine transitions to
`WINDING_DOWN` and the governor rejects all entry intents. Exits remain permitted.

**R-12.4.b** — At `force_flatten_at` (default **15:55 ET**) the engine MUST submit exit orders for
every open position, escalating per R-10.4.b. This MUST occur regardless of PnL, regardless of the
model's opinion, regardless of an in-progress signal.

**R-12.4.c** — If any position remains open at `session_close − 60s`, the operator MUST be notified at
**critical** severity (§13.4) and the position MUST be logged as an overnight-risk incident requiring
review before the next session's authorization.

**R-12.4.d** — These times MUST be derived from the exchange calendar, not hardcoded (R-5.4.c). On a
13:00 half-day close, flatten is at 12:55.

### 12.5 Interaction with the kill switch

**R-12.5.a** — `HALTED` MUST: reject all new intents; cancel every working order; and, per
`halt_flatten_positions` (default **true**), submit exit orders for all open positions. Cancel first,
then flatten — cancelling after submitting exits can cancel the exit.

**R-12.5.b** — Halt-originated flatten orders MUST pass through the same single path (R-10.1.a) with a
`halt_exit=True` flag that the governor recognizes as exempt from Group 1 rules **only** for
risk-reducing orders. The exemption MUST be narrow, explicit, and independently tested: an order that
would increase exposure MUST still be rejected while halted.

### 12.6 Verification

**R-12.6.a** — 100% **branch** coverage on `services/engine/risk/`, enforced in CI with
`--cov-fail-under=100 --cov-branch` scoped to that package. Not line coverage. Not 99%.

**R-12.6.b** — Property-based tests (Hypothesis) MUST assert invariants that hold for **all** generated
inputs:
- An approved order never increases any exposure metric beyond its configured limit.
- An approved order is never larger than the requested intent (R-12.1.d).
- With no grant, no input produces `Approved` (except a halt-exit, R-12.5.b).
- With `halt.active`, no input produces `Approved` except a risk-reducing halt-exit.
- `evaluate` never raises for any generated input (R-12.1.c).
- `evaluate` is deterministic: the same inputs always produce the same output.
- Approving order A then order B never yields exposure exceeding the limit, for all A, B orders.

**R-12.6.c** — Each rule MUST have at least one test that fails if the rule is deleted. A mutation test
run (`mutmut` or equivalent) over `risk/` MUST show zero surviving mutants, run at least at each phase
gate. Coverage proves the line executed; mutation testing proves the assertion mattered.

**R-12.6.d** — Risk rule changes require: the ADR, the tests, and explicit operator sign-off recorded
in the PR. No exceptions, including for changes that only *tighten* a limit.

---

## 13. Control plane: authorization, kill switch, notifications

### 13.1 Authorization

#### 13.1.1 Model

An **authorization grant** is the operator's explicit, scoped, time-boxed permission to trade.

```
authorization_grants
  id, created_at, granted_at, expires_at, revoked_at, revoked_reason
  rank_run_id            -- which set of 10 this covers
  symbols                -- the explicit list, frozen at grant time
  max_capital_usd        -- ceiling on deployed notional
  max_orders             -- ceiling on order count
  sides_allowed          -- {long}, {short}, or {long, short}
  granted_by_method      -- 'web' | 'telegram'
  granted_from_ip, user_agent
  mfa_verified_at
  config_hash, model_ids
```

**R-13.1.a** — `expires_at - granted_at <= 24 hours`, enforced by a Postgres `CHECK` constraint, the
API validator, and the risk governor (R-12.2.c). Three independent enforcement points because this is
the rule that bounds the blast radius of every other failure.

**R-13.1.b** — The default grant lifetime MUST be **until today's session close**, not 24 hours. 24h is
the ceiling, not the default. The UI presents session-close as the pre-selected option.

**R-13.1.c** — Grants MUST be **scoped to an explicit symbol list**, frozen at grant time from the
rank run the operator reviewed. If the model later changes its mind about which 10, that requires a new
grant. The operator authorized *those names*.

**R-13.1.d** — No auto-renewal, no rolling window, no "extend" operation (R-3.4.c). Extending is
granting a new grant, with a new review, recorded separately.

**R-13.1.e** — Granting MUST require re-authentication: a TOTP code (§16.2) in the web flow, or the
challenge-response in the Telegram flow (§13.6.2). A session cookie alone is not sufficient.

**R-13.1.f** — Revocation MUST take effect within `halt_poll_interval_ms` and MUST cancel working
orders. Revoking is not a halt (positions may still be managed to exit), but no new entries occur.

**R-13.1.g** — Grant creation, use, and expiry MUST each write `audit_log` rows.

#### 13.1.2 What the operator sees before granting

The authorization screen MUST show, without scrolling on a phone: the 10 symbols with their Stage B
scores and one-line reason; today's proposed capital and the resulting maximum loss if every position
stopped out simultaneously (portfolio heat, R-12.2.s); the active model id and its last drift status;
the data quality gate result; the date of the last successful kill-switch drill; and the environment
(paper/live) in unmissable type.

**R-13.1.h** — The **maximum plausible loss** figure MUST be displayed on the authorization screen. An
authorization flow that shows upside without the paired downside is a dark pattern, even when the
operator is also the author.

### 13.2 Kill switch

#### 13.2.1 Requirement

**R-13.2.a** — From the moment the operator initiates a halt, within **10 seconds at p99**: the engine
is in `HALTED`, all working orders have a cancel acknowledged by the broker, and no new order can be
submitted. Measured end-to-end and recorded per activation in `kill_switch_events`.

**R-13.2.b** — The 10-second SLO MUST be measured in every drill (§13.3) and the measurement MUST be
of the *full* path including message delivery, not just Atlas's internal processing.

#### 13.2.2 Three independent paths

| Path | Mechanism | Works when |
|---|---|---|
| **1 · Telegram** | Operator sends `/halt` to the Atlas bot → Telegram webhook → API → durable halt state + `NOTIFY` | Frontend down, Vercel down, operator has no data connection beyond messaging |
| **2 · Web** | Big red button on every page of the frontend → `POST /v1/halt` | Normal case, fastest UI |
| **3 · Twilio SMS** | Operator texts `HALT` to the Atlas number → Twilio webhook → API | Telegram down, no data connection, cellular only |

**R-13.2.c** — The halt signal MUST be delivered to the engine by **two mechanisms simultaneously**:
a Postgres `LISTEN/NOTIFY` push (fast path, typically < 100ms) **and** a poll of the durable
`halt_state` row every `halt_poll_interval_ms` (default **250ms**, guaranteed path). The engine checks
the in-process flag before every order submission (R-10.1.b step 3). Push alone is not sufficient —
a dropped connection loses the notification; poll alone is not fast enough under pathological load.

**R-13.2.d** — Halt state MUST be **durable and default-deny on ambiguity**: if the engine cannot read
`halt_state` for `halt_state_unreadable_halt_seconds` (default **5s**), it MUST treat itself as halted.
An engine that cannot verify it is allowed to trade is not allowed to trade.

**R-13.2.e** — The three paths MUST NOT share a single point of failure beyond the database and the
engine itself. In particular, path 1 and path 3 MUST NOT depend on Vercel, and all three MUST NOT
depend on the operator being logged into a browser session.

**R-13.2.f** — There MUST additionally be a **dead-man's switch**: the engine writes a heartbeat every
`heartbeat_interval_seconds` (default 5s). If the API observes no heartbeat for
`heartbeat_timeout_seconds` (default 30s) during a session with an active grant, it MUST set halt state
and notify the operator at critical severity.

#### 13.2.3 Halt semantics

**R-13.2.g** — On halt the engine MUST, in order: (1) set the in-process flag so no further submission
occurs; (2) cancel all working orders; (3) if `halt_flatten_positions`, submit exits per R-12.5;
(4) confirm cancels with the broker; (5) notify the operator that the halt completed, with the measured
elapsed time and the resulting position state.

**R-13.2.h** — Exiting `HALTED` MUST require an explicit operator action with re-authentication, MUST
NOT be possible from the same message that could be an accidental repeat, and MUST write `audit_log`.
Any pre-existing grant is **void** after a halt; resuming requires a new grant.

**R-13.2.i** — The halt path MUST be the simplest code in the repository, MUST have no dependency on
the model, the scanner, or the feature pipeline, and MUST be exercised by its own test suite that runs
even when everything else is failing.

### 13.3 Weekly drill

**R-13.3.a** — A kill-switch drill MUST run **weekly**, against paper, with open positions present,
exercising **each** of the three paths in rotation and recording the measured end-to-end latency in
`kill_switch_drills`.

**R-13.3.b** — The drill MUST be at least partly **operator-performed**, not purely automated: an
automated test proves the code path works, but the requirement in R-3.3.a is that *the operator* can
halt from their phone. Muscle memory is part of the control. At minimum one drill per month is
performed manually end-to-end from the phone.

**R-13.3.c** — If the most recent successful drill is older than `drill_max_age_days` (default **8**):
the frontend MUST show a persistent warning, the operator MUST be notified, and in live the system MUST
refuse to issue a new authorization grant. The kill switch is only a control if it is known to work.

**R-13.3.d** — A drill that exceeds the 10s SLO MUST be recorded as a failure, MUST notify at critical
severity, and MUST block live authorization until a subsequent drill passes.

### 13.4 Outbound notifications

| Severity | Channels | Examples |
|---|---|---|
| **critical** | SMS + email + push, bypass quiet hours, escalate if unacknowledged in 5 min | Halt triggered; position/state discrepancy (R-10.6.b); daily loss limit breached; position open near close (R-12.4.c); heartbeat lost; drill failed |
| **high** | SMS + email | Candidates ready for authorization; grant expiring in 30 min with positions open; order rejected for an unexpected reason; drift alert |
| **normal** | email | End-of-day summary; scan completed; model retrained; drill passed |
| **low** | in-app only | Individual fills, routine state transitions |

**R-13.4.a** — Twilio for SMS, Resend for email. Both behind `NotifierPort` with a durable outbox:
notifications are written to `notifications` in the same transaction as the triggering event, and a
separate dispatcher delivers them with retries. A notification lost to an API timeout is a notification
that did not happen.

**R-13.4.b** — **Critical notifications MUST NOT be rate-limited or batched.** All others MUST be, to
`max_notifications_per_hour` (default 10), with overflow collapsed into a digest. An operator who
learns to ignore Atlas's messages does not have a working alerting system.

**R-13.4.c** — Every notification MUST state the environment (paper/live) as its first token, and MUST
contain a deep link to the relevant screen.

**R-13.4.d** — Delivery failure of a **critical** notification MUST itself escalate: retry on the
alternate channel immediately, and surface the failure in the UI.

**R-13.4.e** — Quiet hours MAY suppress `normal` and `low` outside 07:00–22:00 ET. They MUST NOT apply
to `critical` or `high`.

### 13.5 Notification content

**R-13.5.a** — Every notification MUST be actionable: what happened, what it means for money, and what
the operator can do. "Order rejected" is not acceptable; "PAPER · AAPL entry rejected by R-12.2.x
(spread 31bps > 25bps limit). No position taken. 3 candidates remain." is.

**R-13.5.b** — Monetary amounts MUST be exact, formatted to cents, and labelled realized or unrealized.

### 13.6 Inbound webhooks

Inbound webhooks are how the kill switch reaches Atlas from a phone. They are the highest-value attack
surface in the system: an unauthenticated halt endpoint is a denial-of-service on the operator's
trading, and an unauthenticated *resume* endpoint would be far worse.

#### 13.6.1 Telegram

**R-13.6.a** — The Telegram webhook MUST verify the `X-Telegram-Bot-Api-Secret-Token` header against a
secret set when registering the webhook, using a constant-time comparison. A mismatch returns 200 with
no action (never a 401, which confirms the endpoint exists) and increments a security counter.

**R-13.6.b** — The webhook MUST accept commands **only** from a single allowlisted `chat_id`, configured
explicitly. Any other chat is silently ignored and logged as a security event. Bot tokens leak; the
chat allowlist is the real control.

**R-13.6.c** — The endpoint MUST be idempotent on Telegram's `update_id` — Telegram retries, and a
retried `/halt` must not double-execute.

**R-13.6.d** — Supported commands: `/halt` (immediate, no confirmation — hesitation is the failure mode
this exists to prevent), `/status`, `/positions`, `/flatten`, `/authorize <code>`, `/resume <code>`.
Destructive-in-reverse commands (`/resume`, `/authorize`) MUST require a challenge-response code sent
by a **different** channel (email), never a plain confirmation in the same chat.

**R-13.6.e** — The webhook MUST respond within 2 seconds and MUST do the halt write *before*
responding. Dispatching to a background task and returning 200 optimistically is how a halt gets lost.

#### 13.6.2 Twilio

**R-13.6.f** — If inbound SMS is enabled, every request MUST have its `X-Twilio-Signature` validated
against the auth token and the exact public URL, rejecting on failure. Unsigned inbound SMS handling
MUST NOT be deployed, including in paper.

**R-13.6.g** — The sending number MUST be on a single-entry allowlist. Caller ID is spoofable, which is
why signature validation is also required and why `HALT` is the only command permitted over SMS —
the failure mode of a spoofed halt is a stopped system, which is acceptable; a spoofed resume is not.

#### 13.6.3 Both

**R-13.6.h** — All webhook endpoints MUST be rate-limited per source, MUST log every request
(including rejected ones) to `audit_log` with the outcome, MUST have a request-body size cap, and MUST
NOT echo any internal state to an unverified caller.

**R-13.6.i** — Webhook secrets MUST be rotatable without downtime: the verifier accepts the current and
previous secret during a rotation window.

---

## 14. API surface

FastAPI, `services/api/`. All routes under `/v1`. OpenAPI 3.1 schema published at `/v1/openapi.json`
and used to generate the frontend client (§15.6).

### 14.1 Conventions

**R-14.1.a** — Every response envelope MUST include `environment` (`paper`/`live`), `server_time`
(UTC ISO-8601), and `config_hash`. The frontend renders the environment on every screen (R-11.1.d).

**R-14.1.b** — All money in JSON MUST be a **string** decimal (`"1234.56"`), never a JSON number.
IEEE-754 in JavaScript is exactly the class of bug R-3.6.a exists to prevent, and it does not stop at
the API boundary.

**R-14.1.c** — Mutating endpoints MUST require an `Idempotency-Key` header and MUST store the result
keyed by it for 24 hours.

**R-14.1.d** — Errors MUST follow RFC 9457 Problem Details, and a risk rejection MUST include the
rule ID (`R-12.2.x`) so the UI can explain it and the operator can grep the spec.

### 14.2 Routes

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/v1/health` | none | Liveness. No internal state. |
| `GET` | `/v1/system/status` | session | Engine state, heartbeat age, data-quality gate, drill age, active models, config hash |
| `GET` | `/v1/scans/latest` | session | Latest scan run + the 50, with scores |
| `GET` | `/v1/scans/{id}/candidates` | session | Full candidate list incl. `rejected_by` (R-7.1.b) |
| `GET` | `/v1/ranks/latest` | session | The 10, with Stage B scores and explanations |
| `POST` | `/v1/authorizations` | session + **TOTP** | Create a grant (§13.1). Validates ≤24h |
| `GET` | `/v1/authorizations/active` | session | Current grant + remaining time |
| `DELETE` | `/v1/authorizations/{id}` | session | Revoke (R-13.1.f) |
| **`POST`** | **`/v1/halt`** | session **or** webhook-verified | **Kill switch.** Highest priority route |
| `POST` | `/v1/resume` | session + **TOTP** | Leave `HALTED` (R-13.2.h) |
| `POST` | `/v1/flatten` | session + TOTP | Exit all positions without halting |
| `GET` | `/v1/positions` | session | Live positions with unrealized PnL |
| `GET` | `/v1/orders` | session | Orders with state, rejections, rule IDs |
| `GET` | `/v1/pnl/daily` | session | Daily PnL series |
| `GET` | `/v1/models` / `POST /v1/models/{id}/activate` | session (+TOTP for activate) | Registry, activation (R-9.8.c) |
| `GET` | `/v1/backtests` / `{id}` | session | Backtest runs and reports |
| `GET` | `/v1/drills` / `POST /v1/drills` | session | Drill history; start a drill (§13.3) |
| `GET` | `/v1/audit` | session | Paginated audit log |
| `GET` | `/v1/events` (SSE) | session | Live event stream for the UI |
| `POST` | `/v1/webhooks/telegram` | secret token | §13.6.1 |
| `POST` | `/v1/webhooks/twilio` | signature | §13.6.2 |

**R-14.2.a** — `POST /v1/halt` MUST be the simplest handler in the codebase: verify caller, write halt
state, `NOTIFY`, return. No model loading, no joins, no external calls. It MUST be served by a route
that stays available if the rest of the API is degraded, and MUST have a dedicated latency SLO
(p99 < 300ms server-side) monitored separately.

**R-14.2.b** — The API MUST NOT expose any endpoint that places, modifies, or cancels a specific
broker order directly (R-4.2.b). `/v1/flatten` writes an intent the engine executes through R-10.1.b.

### 14.3 Realtime

Server-Sent Events from `/v1/events`, backed by Postgres `LISTEN/NOTIFY`, for: engine state changes,
new fills, position updates, PnL ticks, risk rejections, notifications, halt state.

**R-14.3.a** — The UI MUST NOT rely solely on SSE for halt state. The halt indicator MUST also poll
every 2 seconds, and MUST render "unknown" rather than "running" when it cannot determine state.
Showing a stale green light is worse than showing no light.

---

## 15. Frontend

Next.js 15 App Router, TypeScript `strict`, on Vercel.

### 15.1 Principles

The operator uses this on a phone, in a hurry, sometimes while the market is moving against them. It is
an instrument panel, not a dashboard product.

**R-15.1.a** — The **halt control MUST be present on every screen**, fixed position, reachable without
scrolling, on every viewport. It is the only element with that guarantee.

**R-15.1.b** — Halting MUST take at most **two taps** (press, confirm) and the confirm MUST NOT be a
typed word or a slider. Friction on the stop button is a defect.

**R-15.1.c** — The three questions in §1.4 MUST each be answerable in under five seconds from a cold
open on a phone.

### 15.2 Visual system

- **Manrope** throughout, loaded via `next/font/google` with `display: 'swap'`, variable weight,
  subset latin. Tabular numerals (`font-variant-numeric: tabular-nums`) for every numeric column —
  prices that shift horizontally as they tick are unreadable.
- Tailwind v4, design tokens as CSS custom properties on `:root`, redefined under
  `@media (prefers-color-scheme: dark)` and `[data-theme]`.
- Dark theme is the default; the operator is looking at this at 09:31 and at 15:54.
- Gains/losses MUST NOT be distinguished by colour alone — sign, arrow glyph, and colour together
  (red/green is the most common colour-vision deficiency).
- Never animate a number transition in a way that obscures the current value.

**R-15.2.a** — **Live mode MUST be visually unmistakable**: a persistent top border in a distinct
colour, an "LIVE" badge in the header, and the environment word in every notification and page title.
The operator must never act on a paper screen believing it is live, or the reverse.

### 15.3 Routes

| Route | Contents |
|---|---|
| `/` | Engine state, today's PnL (realized + unrealized), open positions, active grant countdown, system health strip, halt button |
| `/authorize` | The 10 candidates, capital slider, max-loss figure (R-13.1.h), TOTP, grant button |
| `/scan` | Today's 50 with scores; searchable full universe view with `rejected_by` |
| `/positions` | Open + closed today, entry reason, stop distance, time in trade, exit reason |
| `/orders` | Every order incl. rejections with rule IDs and plain-English explanations |
| `/research` | Backtest runs, model cards, drift charts, feature importance |
| `/history` | Daily PnL, equity curve, per-symbol and per-hour attribution |
| `/system` | Data quality gate, drill history, config hash, model versions, heartbeat, reconciliation status |
| `/audit` | Searchable audit log |

### 15.4 Data display

**R-15.4.a** — Every displayed timestamp MUST carry a timezone label (R-5.4.b).

**R-15.4.b** — Stale data MUST be visually marked. If the last update is older than 5 seconds during
market hours, the affected values grey out with the age shown. A stale number presented as current is
how an operator makes a decision on a market that has moved.

**R-15.4.c** — Money MUST be rendered from the API's string decimals via a `Decimal` library
(`decimal.js` or `dinero.js`). `parseFloat` on a money string is a defect (R-14.1.b).

**R-15.4.d** — Charts follow the repository's data-visualization conventions: no chartjunk, no dual
y-axes, direct labelling over legends where feasible, and an explicit statement of what is being
measured. Price charts use Lightweight Charts; everything else uses Recharts.

### 15.5 Explanation

**R-15.5.a** — Every decision surfaced in the UI MUST be explainable in one tap: why this symbol was
selected (Stage A score components, Stage B rank, top SHAP contributors), why an entry did or did not
fire (Stage C probability vs. threshold), why an order was rejected (rule ID + plain English). A system
the operator cannot interrogate is a system they cannot trust enough to authorize.

### 15.6 The generated client

**R-15.6.a** — `web/lib/api/` is **generated** from the OpenAPI schema (`openapi-typescript` +
`openapi-fetch`) by `npm run generate:api`. It MUST NOT be hand-edited. CI regenerates it and fails if
the working tree differs — a drifted client is a class of bug that shows up as a wrong number on the
screen the operator is deciding from.

**R-15.6.b** — No business logic in the frontend. No risk calculation, no sizing, no threshold
evaluation. The frontend renders state the backend computed. Two implementations of a risk figure is
one implementation too many.

### 15.7 Auth in the browser

**R-15.7.a** — Supabase Auth with email + TOTP. Session tokens in httpOnly, Secure, SameSite=Strict
cookies. No tokens in `localStorage`.

**R-15.7.b** — Sensitive actions (authorize, resume, flatten, activate model) require a fresh TOTP
regardless of session age.

---

## 16. Security

### 16.1 Threat model

Single operator, no other users, but the consequence of compromise is direct financial loss. Threats
worth defending against, in order:

1. **Credential leakage** — live API keys in a repo, a log, a CI artifact, an error message, or an MCP
   config. Highest likelihood, highest impact.
2. **Unauthorized halt-state manipulation** — anyone who can call `/v1/resume` or forge a grant.
3. **Accidental live trading** — a paper/live mixup, by far the most likely way this project loses
   money in practice.
4. **Supply chain** — a malicious dependency in the engine's tree.
5. **Data poisoning** — corrupted market data producing catastrophic orders (mitigated by R-12.2.y).
6. Generic web application attacks against the frontend/API.

### 16.2 Authentication

**R-16.2.a** — Exactly one user account exists. Public sign-up MUST be disabled in Supabase Auth.
Creating the account is a manual, documented, one-time operation.

**R-16.2.b** — TOTP MFA MUST be enrolled and required. Recovery codes stored offline, out of band.

**R-16.2.c** — Service-to-service auth (engine → API, worker → API) MUST use separate credentials with
least privilege, rotated quarterly, never the operator's session.

### 16.3 Secrets matrix

| Secret | Local dev | CI | Fly `api`/`engine` (paper) | Fly `api`/`engine` (live) | MCP config |
|---|---|---|---|---|---|
| Alpaca **paper** key/secret | ✅ | ✅ | ✅ | ✅ | ✅ |
| Alpaca **live** key/secret | ❌ | ❌ | ❌ | ✅ **only here** | ❌ |
| Supabase service role key | ❌ | ❌ | ✅ | ✅ | ❌ |
| Supabase anon key | ✅ | ✅ | ✅ | ✅ | ❌ |
| Twilio auth token | ❌ | ❌ | ✅ | ✅ | ❌ |
| Resend key | ❌ | ❌ | ✅ | ✅ | ❌ |
| Telegram bot token + webhook secret | ❌ | ❌ | ✅ | ✅ | ❌ |

**R-16.3.a** — Live credentials exist **only** in the Fly secret store for the production `api` and
`engine` apps (R-3.1.c). They are never printed, never logged, never in an error message, never in a
`.env` file, and never in a developer's shell history.

**R-16.3.b** — `.env.example` MUST list every variable name with an empty value and a comment pointing
here. It MUST NOT contain a real value, including a paper one.

**R-16.3.c** — Secret scanning (`gitleaks` or GitHub secret scanning with push protection) MUST run on
every commit and MUST block the push. A pre-commit hook MUST run the same check locally.

**R-16.3.d** — If a live key is ever exposed, in any form, the runbook (Appendix F.5) is: revoke at
Alpaca first, rotate, then investigate. Revoke first, always.

**R-16.3.e** — Logs MUST pass through a redaction filter that masks anything matching credential
patterns, applied at the formatter so it cannot be bypassed by an ad-hoc `print`.

### 16.4 Database

**R-16.4.a** — RLS enabled on **every** table. The anon role has no access to anything. The
authenticated role has read access to operator-facing views only. All writes go through the service
role from the backend.

**R-16.4.b** — The frontend MUST NOT connect to Supabase Postgres directly for domain data. It talks to
the API. Supabase Realtime MAY be used for read-only UI subscriptions on explicitly published views.

**R-16.4.c** — Least-privilege database roles: `atlas_engine` (read/write trading tables), `atlas_api`
(read most, write control plane), `atlas_worker` (read/write data + model tables). None of them may
`UPDATE` or `DELETE` `audit_log` (R-3.7.b).

**R-16.4.d** — Backups: Supabase PITR enabled; a weekly logical dump of control-plane and trading
tables to a separate bucket; restore tested quarterly. An untested backup is not a backup.

### 16.5 Application

- HTTPS only, HSTS, CSP without `unsafe-inline`, no third-party scripts on authenticated pages.
- All input validated by Pydantic at the boundary; parameterized SQL only.
- Rate limiting on all endpoints; stricter on auth and webhooks.
- Dependency scanning (`pip-audit`, `npm audit`) in CI; the engine's tree reviewed at each phase gate.
- `services/engine/risk/` and `libs/atlas_core/` require review on every change (CODEOWNERS).

### 16.6 Operational

**R-16.6.a** — Before **every** deploy to live, a pre-deploy check MUST verify: `ALPACA_ENV` matches
the intended app, the account endpoint confirms paper/live nature (R-11.1.b), the active model is
promoted, the last drill is within `drill_max_age_days`, and the data quality gate passed. Automated,
in the deploy pipeline, blocking.

**R-16.6.b** — Live deploys MUST NOT occur during market hours while positions are open, except for a
halt-path hotfix. Enforced by the deploy pipeline checking engine state.

---

## 17. Observability and audit

### 17.1 Logging

**R-17.1.a** — Structured JSON logs. Every line carries: `timestamp` (UTC), `level`, `service`,
`environment`, `git_sha`, `config_hash`, `correlation_id`, `session_date`, and where applicable
`symbol`, `order_id`, `intent_id`, `rule_id`.

**R-17.1.b** — A `correlation_id` MUST flow from scan → rank → intent → risk decision → order → fill →
PnL, so a single trade can be reconstructed end to end with one query.

**R-17.1.c** — Log levels: `DEBUG` local only; `INFO` for state transitions and decisions; `WARNING`
for degraded conditions; `ERROR` for failures needing attention; `CRITICAL` for anything that also
pages the operator. Every `CRITICAL` MUST correspond to a notification (§13.4).

### 17.2 Metrics

Prometheus-compatible, scraped by Fly/Grafana Cloud.

| Metric | Type | Alert |
|---|---|---|
| `atlas_engine_state` | gauge | Unexpected state during session |
| `atlas_halt_latency_seconds` | histogram | **p99 > 10s — page** (R-3.3.a) |
| `atlas_heartbeat_age_seconds` | gauge | > 30s during session — page (R-13.2.f) |
| `atlas_orders_submitted_total{result}` | counter | Rejection rate > 20% |
| `atlas_risk_rejections_total{rule_id}` | counter | Spike on any single rule |
| `atlas_broker_errors_total{code}` | counter | Feeds the circuit breaker |
| `atlas_data_staleness_seconds{stream}` | gauge | > 10s during session — page |
| `atlas_position_count`, `atlas_gross_exposure_usd` | gauge | Approaching limits |
| `atlas_daily_pnl_usd` | gauge | Approaching `max_daily_loss_usd` |
| `atlas_scan_duration_seconds` | histogram | > `scan_deadline_seconds` |
| `atlas_model_score_p50`, `atlas_feature_psi{feature}` | gauge | Drift (R-9.9.b) |
| `atlas_fill_slippage_bps` | histogram | Persistent bias vs. model (R-8.3.e) |
| `atlas_reconciliation_discrepancies_total` | counter | **Any — page** (R-10.6.b) |
| `atlas_drill_age_days` | gauge | > 8 — warn (R-13.3.c) |

**R-17.2.a** — Alerts that page the operator MUST be limited to conditions that require action within
minutes. Everything else is a dashboard. Alert fatigue is a safety failure, not an annoyance.

### 17.3 Tracing

OpenTelemetry spans on the decision path: scan → rank → Stage C → risk → submit → fill.
**R-17.3.a** — The halt path MUST be traced and its end-to-end latency recorded per activation.

### 17.4 The audit log

**R-17.4.a** — `audit_log` columns: `id`, `occurred_at`, `actor` (`operator` | `engine` | `worker` |
`api` | `webhook:telegram` | `webhook:twilio`), `actor_detail`, `action`, `entity_type`, `entity_id`,
`before` (jsonb), `after` (jsonb), `correlation_id`, `environment`, `git_sha`, `config_hash`,
`request_ip`, `reason`.

**R-17.4.b** — Append-only, enforced by a trigger that raises on `UPDATE` and `DELETE` for **all**
roles including the table owner. Tested by a migration test that attempts both and asserts failure.

**R-17.4.c** — Auditable actions include at minimum: grant created/used/revoked/expired; halt
triggered/cleared (with path and latency); order intent/approval/rejection/submission/fill/cancel;
position opened/closed; model activated/rolled back; config change; login/MFA/failed auth; webhook
received (accepted or rejected); drill run; data quality gate result; reconciliation discrepancy;
manual intervention of any kind.

**R-17.4.d** — Writes occur in the **same transaction** as the change they describe (R-3.7.a). A code
review checklist item on every PR touching money, position, or authorization state asks: does this
write an audit row in the same transaction?

### 17.5 Daily report

**R-17.5.a** — An end-of-day report MUST be generated and emailed: PnL (realized, unrealized, costs
broken out), every trade with entry/exit reason, risk rejections by rule, model scores vs. outcomes,
any incident, tomorrow's readiness (data gate, drill age, model status). This is the artifact the
operator reviews before authorizing the next day, and it is the primary defence against the failure
mode of a system quietly degrading while nobody looks.

---

## 18. Testing and CI

### 18.1 Layers

| Layer | Scope | Gate |
|---|---|---|
| **Unit** | Pure functions: risk, features, costs, labels, calendar, sizing | Coverage ≥ 90% overall; **100% branch** on `risk/` (R-12.6.a) |
| **Property** | Hypothesis invariants on risk and sizing (R-12.6.b) | Must pass |
| **Leakage** | `tests/leakage/` — L1–L17 of §9.1 | **Must pass. Blocks merge** (R-9.1.a) |
| **Integration** | Adapters against recorded fixtures / Alpaca paper sandbox | Must pass |
| **Golden** | Backtest reproducibility, scan determinism (R-7.1.a, R-8.1.b) | Byte-identical |
| **E2E** | Playwright: authorize → trade (paper) → halt → verify | Must pass |
| **Drill** | Automated weekly kill-switch drill (§13.3) | SLO enforced |
| **Mutation** | `mutmut` over `risk/` (R-12.6.c) | Zero survivors, at each phase gate |

### 18.2 Determinism

**R-18.2.a** — Every test MUST be deterministic. Seeds fixed and recorded; time injected through
`ClockPort` or `freezegun`; no test reads the wall clock or the network. A flaky test in a
safety-critical suite gets *fixed*, never retried or skipped.

**R-18.2.b** — No test may place an order against a **live** account. Enforced by a conftest fixture
that raises if `ALPACA_ENV == "live"` in any test process.

### 18.3 Fixtures

**R-18.3.a** — A recorded market-data corpus MUST exist covering: a normal day, a high-volatility day,
a half-day, a day with a halt in a held name, a day with a split, a gap-up open, and a day the data
feed was degraded. Every one of these has produced a production incident in systems like this.

### 18.4 Leakage suite

Implements the `Test` column of §9.1 as executable checks. Includes the static AST scan for future-
looking operations (R-6.4.f), the banned-sklearn-splitter grep (R-9.4.c), the `as_of` query lint
(R-6.4.a), the bar alignment assertion (R-6.4.g), and the feature parity test (R-9.2.e).

### 18.5 Frontend

Vitest for units, Playwright for E2E and visual regression on the dashboard and authorization screens,
axe accessibility checks, and an explicit test that the halt button is present and reachable on every
route at 375px width (R-15.1.a).

### 18.6 Architecture tests

**R-18.6.a** — `import-linter` contracts enforced in CI:
- `libs/atlas_core/` MUST NOT import from `services/`.
- `services/*/` domain and decision code MUST NOT import vendor SDKs (R-4.3.a).
- Nothing under `services/` may import any MCP client (R-3.8.a / R-19.3.a).
- `services/api/` MUST NOT import `services/engine/execution/` (R-4.2.b).
- Only `execution/submit.py` may reference broker order methods (R-10.1.c).

### 18.7 CI pipeline

On every PR: `ruff check` + `ruff format --check` → `mypy --strict` → import-linter → secret scan →
unit + property → leakage → coverage gates → integration (paper fixtures) → golden runs → build →
frontend lint/type/test → OpenAPI client regeneration diff check (R-15.6.a).

Nightly: full backtest golden run, mutation tests on `risk/`, dependency audit, E2E against paper.

**R-18.7.a** — CI MUST have **no** live Alpaca credentials (R-3.1.c). A CI job that needs the broker
uses paper.

**R-18.7.b** — A failing leakage or risk-coverage check MUST NOT be overridable by a merge-queue
admin bypass. Branch protection configured accordingly.

---

## 19. Tooling: the Alpaca MCP and other connectors

### 19.1 What the MCP is for

The Alpaca MCP server is a **first-class part of Phases 0–4**. It is how you find out what the data
actually looks like before committing to a pipeline design, and it is dramatically faster than writing
a script for every question.

**R-19.1.a** — The proof of concept (Phase 0) MUST be run through the MCP before any engine code is
written: place and cancel a paper order, read account and positions, pull bars for a handful of
symbols, pull a snapshot, and confirm the shape of every field Atlas intends to depend on.

**R-19.1.b** — Use it to: validate bar data against expectations before building ingest; sanity-check
scanner output against live market state (§7.6); investigate what the model got wrong on a given day;
inspect corporate-action handling; check shortability and halt behaviour on real symbols.

**R-19.1.c** — **Anything learned through the MCP that informs a decision MUST be written down** in
`docs/research/YYYY-MM-DD-topic.md` or `docs/SOURCES.md`, with the date, the question, the observation,
and the conclusion. A chat transcript is not a durable artifact: it is not reviewable, not greppable,
not versioned, and not available to the next person. If it changed the design, it goes in the repo.

**R-19.1.d** — Every external fact this specification depends on — fee rates, data entitlements, API
limits, regulatory status (R-2.4.b) — MUST have an entry in `docs/SOURCES.md` with the source and the
date checked. Facts decay.

### 19.2 MCP configuration

**R-19.2.a** — `.mcp.json` MUST reference **paper credentials only**, and the paper base URL. Live
credentials in an MCP configuration would put live trading behind a natural-language interface with no
risk governor, which is the exact failure this specification is built to prevent.

**R-19.2.b** — `.mcp.json` MUST NOT contain literal secrets; it references environment variables. The
file is committed; the values are not.

**R-19.2.c** — The MCP's paper account SHOULD be a **separate paper account** from the one the engine
uses for paper trading, so that exploratory orders never contaminate the paper track record that
Phase 7's soak test depends on.

### 19.3 The boundaries

Two hard boundaries, both stated in §3.8 and repeated here because they are easy to erode:

**R-19.3.a** — **No MCP server or connector may be referenced anywhere under `services/`.** Not
imported, not shelled out to, not called over HTTP. This applies to the Alpaca MCP and to every other
MCP server or connector that may be attached to a development session. The engine reaches Alpaca
through `BrokerPort` and `MarketDataPort` so that order paths remain deterministic, idempotent,
risk-checked, and reproducible in the backtester. Enforced by an import-linter contract and a grep in
CI (R-18.6.a).

**R-19.3.b** — **Bulk historical ingest uses the REST API, not tool calls** (R-6.5.a). It is the same
Alpaca data either way; the difference is pagination, retry, rate-limit handling, checkpointing, and
reproducibility.

**R-19.3.c** — An MCP result MUST NOT be pasted into code as a hardcoded value without recording its
provenance (R-19.1.c). Numbers acquire authority by being in a file; make sure they deserve it.

### 19.4 Other tools

Connectors attached to a development session (GitHub, browsers, documentation servers, anything else)
are subject to R-19.3.a without exception. They are development aids. Nothing in the trading path may
depend on one.

---

## 20. Build phases

Build in order. Each phase ends at a 🔴 **HARD GATE**: stop, run the acceptance criteria, write a status
report to `docs/status/phase-N.md`, and wait for the operator. Do not start phase N+1 because phase N
"is basically done".

The ordering is deliberate and it is the most important structural decision after §4.3. The engine —
the interesting part, the part everyone wants to build first — is **Phase 5**. It is worthless without
a trustworthy backtester, which is worthless without clean point-in-time data. Building the engine
first produces a system that trades confidently on numbers nobody has verified.

| Phase | Name | Rough size |
|---|---|---|
| 0 | Foundations and proof of concept | small |
| 1 | Data platform | **large — budget for it** |
| 2 | Stage A scanner | medium |
| 3 | Backtester and cost model | large |
| 4 | Features, labels, and the ML layer | large |
| 5 | Execution engine and risk governor (paper) | large |
| 6 | Control plane: authorization, kill switch, notifications | medium |
| 7 | Frontend and the paper soak | medium |
| 8 | 🔴🔴 Live | gated |

### 20.1 Phase 0 — Foundations and proof of concept

Repository skeleton per §5.1; `pyproject.toml`, lint/type/test config; CI pipeline running on an empty
test suite; Supabase project with the first migrations; Fly apps created (not yet deployed); typed
config with `ALPACA_ENV` enforcement (R-11.1.a); `.mcp.json` with paper credentials; the MCP proof of
concept (R-19.1.a) written up in `docs/research/`.

**Acceptance:**
- CI green: `ruff`, `mypy --strict`, `pytest`, secret scan, import-linter.
- A test proves the process exits non-zero when `ALPACA_ENV` is missing, empty, or invalid.
- A paper order has been placed and cancelled through the MCP, and the POC write-up exists.
- `docs/SOURCES.md` has entries for: data feed entitlement/pricing, fee rates, rate limits, PDT status.
- `.env.example` complete with no values (R-16.3.b).

🔴 **GATE 0** — nothing proceeds without a working CI that would catch a secret.

### 20.2 Phase 1 — Data platform

§6 in full: schema, bulk historical ingest, nightly ingest, universe snapshots, corporate actions,
calendar, Parquet archive + manifests, DuckDB research access, the data quality gate, and the
point-in-time machinery.

**Acceptance:**
- 10 years of daily bars and 3 years of minute bars for the top ~1,500 names ingested and verified.
- Universe snapshots exist for every date in the history and **include delisted symbols** — demonstrate
  by naming five symbols that were tradeable in 2023 and are not now, and showing they are present.
- The as-of adjustment is correct: pick three symbols that split during the period; show the price
  series as it appeared *before* the split and *after*, and show that a query as of a pre-split date
  returns unadjusted prices (R-6.4.d, R-6.4.e).
- Data quality gate runs nightly, persists results, and **blocks** on a deliberately corrupted input.
- Bar alignment convention verified by test (R-6.4.g).
- Ten random symbol-days cross-checked against the Alpaca MCP and against a second source where
  possible; discrepancies documented in `docs/research/`.
- Ingest is resumable: kill it mid-run and show it resumes from the checkpoint.

🔴 **GATE 1** — this is the phase most likely to be declared done early. It is not done until the
as-of adjustment demonstration above works. Everything downstream inherits any error here.

### 20.3 Phase 2 — Stage A scanner

§7 in full, running against historical data and live paper.

**Acceptance:**
- Scanner produces 50 candidates for any historical date in under `scan_deadline_seconds`.
- Determinism: same date, same config → byte-identical output across 10 runs (R-7.1.a).
- `rejected_by` populated for every symbol in the universe (R-7.1.b).
- Two years of historical scans run; survivor-count distribution, turnover, and next-day realized
  range vs. rejected population reported.
- Evidence the liquidity filters bind (§7.6).
- Twenty days spot-checked against the MCP; write-up in `docs/research/`.
- Thin-day behaviour (R-7.4.c) and `regime_warning` (R-7.4.d) both demonstrated on real dates.

🔴 **GATE 2**

### 20.4 Phase 3 — Backtester and cost model

§8 in full, built on the simulated ports (R-8.2.a). No ML yet — backtest a trivial baseline strategy
(e.g. "buy the top Stage A name at 09:45, exit at the time stop") purely to exercise the machinery.

**Acceptance:**
- Backtester drives unmodified engine decision code through simulated ports.
- Cost model implemented with dated fee schedules, spread model, participation-capped fills, latency.
- Reproducibility: the same manifest reproduces byte-identical results (R-8.1.b), verified in CI.
- Walk-forward harness works (R-8.4.a).
- **Deliberate-bug test**: introduce a lookahead (use the close of bar *t* to trade at bar *t*), show
  the backtest's Sharpe leaps, then show `tests/leakage/` catches it. Document it. This is the exercise
  that calibrates everyone's intuition for how easy it is to manufacture a great backtest.
- Capacity analysis at 1×/2×/5×/10× produces sensible degradation.
- Full metric suite (§8.5) rendered as a report.

🔴 **GATE 3** — do not start ML until you trust the thing that will evaluate it.

### 20.5 Phase 4 — Features, labels, and the ML layer

§9 in full: feature store, triple-barrier labelling, purged walk-forward CV, Stage B ranker, Stage C
gate, promotion gates, model registry, model cards.

**Acceptance:**
- 40–80 features implemented, each with a documented hypothesis (R-9.2.a).
- **`test_feature_parity` passes** (R-9.2.e) — this is the gate's centrepiece.
- All of `tests/leakage/` green.
- Labels cost-adjusted and volatility-scaled; stop-first tie-breaking (R-9.3.d) verified by test.
- Purged walk-forward CV implemented; banned splitters absent (R-9.4.c).
- Stage B and Stage C trained; promotion gates evaluated **and the results reported honestly**.
- `stage_a_score` baseline computed and compared (G1). **If G1 fails, report that.** Phase 4 passes on
  an honest negative result plus an ADR; it fails on a positive result obtained by weakening a gate.
- Model cards written (R-9.7.c).

🔴 **GATE 4** — the operator decides here whether the ML layer ships at all (R-9.7.b).

### 20.6 Phase 5 — Execution engine and risk governor (paper)

§10 and §12 in full. The engine state machine, order lifecycle, idempotency, reconciliation, and the
risk governor. **Paper only.**

**Acceptance:**
- Single order path verified by the AST test (R-10.1.c).
- **100% branch coverage on `services/engine/risk/`** (R-12.6.a) and zero surviving mutants (R-12.6.c).
- All property invariants pass (R-12.6.b).
- Every rule in §12.2 has a test that fails when the rule is deleted.
- Idempotency demonstrated: simulate a submit timeout, show exactly one position results (R-10.5.b).
- Reconciliation demonstrated: inject a broker-side discrepancy, show `HALTED` + notification.
- Force-flatten demonstrated, including on a simulated half-day (R-12.4.d).
- Crash recovery demonstrated: kill the engine with positions open, show it restarts into
  `WINDING_DOWN` and does not open new positions (R-4.6.c).
- Singleton lease demonstrated: start a second engine, show it exits non-zero (R-4.2.a).
- Ten consecutive paper sessions traded end to end with no manual intervention.

🔴 **GATE 5**

### 20.7 Phase 6 — Control plane

§13 in full: authorization grants, the three kill-switch paths, the dead-man's switch, drills,
notifications, webhooks.

**Acceptance:**
- Grants enforce ≤24h at all three enforcement points; prove it by attempting a 25-hour grant against
  each independently (R-13.1.a).
- All three kill-switch paths work and are measured; **p99 < 10 seconds end to end** (R-13.2.a).
- Halt works with the frontend entirely offline (R-13.2.e) — demonstrate by taking Vercel out.
- Halt works with `LISTEN/NOTIFY` disabled, via poll alone (R-13.2.c).
- Unreadable halt state fails closed (R-13.2.d).
- Dead-man's switch demonstrated by killing the engine (R-13.2.f).
- Webhook auth demonstrated: wrong Telegram secret ignored, wrong `chat_id` ignored, bad Twilio
  signature rejected, replayed `update_id` not double-executed.
- First weekly drill recorded; the staleness warning demonstrated by backdating a drill record.
- Notifications delivered on both channels; critical path bypasses rate limits.

🔴 **GATE 6** — R-3.3.a is verified here or it is not verified anywhere.

### 20.8 Phase 7 — Frontend and the paper soak

§15 in full, then a sustained paper run.

**Acceptance:**
- All routes built; halt button present and reachable on every route at 375px (R-15.1.a).
- Generated API client with no hand edits; CI diff check passes (R-15.6.a).
- The three questions in §1.4 answerable in under five seconds each, timed on a phone.
- Explanation views complete (R-15.5.a).
- Live-mode visual treatment implemented and reviewed against a paper screen side by side (R-15.2.a).
- **A 30-consecutive-trading-day paper soak** with: daily reports generated, weekly drills passed,
  zero unexplained reconciliation discrepancies, zero unhandled exceptions in the engine, and realized
  slippage within the modelled range (R-8.3.e). A failure resets the 30-day clock.

🔴 **GATE 7**

### 20.9 Phase 8 — 🔴🔴 Live

Live trading. Eight gates, all of which MUST pass, evidenced in `docs/status/phase-8-gates.md`, each
signed off explicitly by the operator.

| # | Gate | Evidence required |
|---|---|---|
| **G1** | All prior phase gates passed, with their status reports | Links to `docs/status/phase-0..7.md` |
| **G2** | 30+ consecutive paper trading days completed with no unexplained discrepancy, no unhandled engine exception, and all daily reports generated | Soak report, incident log |
| **G3** | Paper results are consistent with the backtest: realized PnL within the backtest's expected distribution, and realized slippage within the modelled range at 1.5× tolerance | Paper vs. backtest comparison (R-8.3.e) |
| **G4** | Risk governor: 100% branch coverage, zero surviving mutants, all property invariants, every rule individually tested | CI artifact from the exact deploying commit |
| **G5** | Kill switch: four consecutive weekly drills passed, all three paths exercised, p99 < 10s, at least one performed manually from the phone | `kill_switch_drills` export |
| **G6** | Model promoted through all of §9.7 including G1-beats-baseline, shadow-mode period complete (R-9.8.e), model card published | `model_promotions` row + model card |
| **G7** | Security: secret scan clean, live credentials confirmed present **only** in the two production Fly secret stores, RLS verified on every table, backup restore tested, `audit_log` append-only trigger verified | Security checklist, signed |
| **G8** | Operational readiness: runbooks written and walked through (Appendix F), alerting verified end to end, `ATLAS_LIVE_CONFIRMED` procedure documented, **and a written capital plan stating the maximum the operator is prepared to lose** | Runbook sign-off, capital plan |

**R-20.9.a** — Live MUST begin at **minimum viable capital** — the smallest amount that produces
representative fills — for at least 20 trading days before any increase. Position limits scale up only
after a documented review at each step.

**R-20.9.b** — The first live session MUST be supervised by the operator in real time, start to finish,
with the halt path open and tested that morning.

**R-20.9.c** — If any Phase 8 gate fails, **do not go live.** Not "go live smaller", not "go live and
watch it". Fix the gate. §1.5 applies: deciding not to go live on the evidence is a successful outcome,
and this rule is what makes that decision available at the moment it is hardest to make.

---

## 21. Open items for the operator

These MUST be answered by the operator rather than guessed. Each is recorded with its answer and date
in `docs/decisions/` once resolved. Items marked **blocking** must be answered before the phase named.

| # | Question | Blocks | Why it matters |
|---|---|---|---|
| **O-1** | Is the Alpaca **SIP** data feed budget approved (~$99/mo at last check)? | **Phase 1** | R-6.2.a. On IEX-only data the scan ranks 2–3% of the tape. If the answer is no, Stage A must be re-scoped to a smaller universe and the spec amended by ADR — not silently run on partial data |
| **O-2** | What is the **total capital** at risk, and the **maximum acceptable loss** — per day, and cumulative before the project stops? | **Phase 6** (sets risk limits), hard-blocks Phase 8 G8 | Every limit in §12.2 derives from this. "I'll decide later" means the limits are arbitrary |
| **O-3** | ~~Equities or options?~~ **Resolved: equities only** (§2.3, ADR-0002) | — | Confirm the operator accepts this resolution |
| **O-4** | Confirm **PDT status** directly with Alpaca and record it (R-2.4.b) | **Phase 8** | The spec assumes the rule was retired in June 2026 on the operator's statement. That is not evidence, and if it is wrong, §12 needs rule R-12.2.ad enabled |
| **O-5** | **Long-only or long and short** at launch? | Phase 5 | Shorting adds locate/borrow handling, different risk asymmetry, and roughly doubles the Stage A eligibility surface. Long-only is a simpler, safer v1 |
| **O-6** | Is the operator's brokerage account **cash or margin**, and is intraday buying power expected? | Phase 5 | Changes sizing, settlement, and whether R-12.2.p's 100% gross default is achievable |
| **O-7** | **Holding-period intent**: minutes (several trades/day/name) or hours (one or two)? | Phase 4 | Sets `holding_horizon`, the label vertical barrier, feature horizons, and cost sensitivity. Shorter holds mean costs dominate |
| **O-8** | Which **notification channel** is authoritative for critical alerts, and what phone number/email? Does the operator want push in addition to SMS? | Phase 6 | §13.4 routing |
| **O-9** | **Telegram** as the primary inbound control path — acceptable? If not, the alternative is SMS-only, which is slower and less reliable | Phase 6 | §13.2.2 |
| **O-10** | **Tax lot / reporting** expectations — does Atlas need to produce anything beyond the broker's own 1099, e.g. a wash-sale-aware ledger? | Phase 7 | Intraday round trips in the same name generate wash-sale complexity. Out of scope unless requested |
| **O-11** | **Funding mechanism**: the brief mentions connecting a bank account. Atlas does **not** implement ACH or funds movement — funding and withdrawal happen through Alpaca's own interface. Confirm this is acceptable | Phase 0 | Building a money-movement path would add regulatory surface far beyond this scope. Recommended answer: yes, use Alpaca directly |
| **O-12** | **Monitoring budget**: Grafana Cloud free tier, or self-hosted on Fly? | Phase 5 | §17.2 |
| **O-13** | **Time commitment** for the daily authorization step. If the operator cannot reliably do this before 09:30, the design needs revisiting — and the answer is *not* to remove the authorization requirement (R-3.4.c) | Phase 6 | §13.1 |
| **O-14** | What is the **stop condition** for the project as a whole — a cumulative loss, a time limit, or a performance threshold, after which Atlas is turned off and the approach reconsidered? | Phase 8 G8 | Deciding this while calm is worth a great deal more than deciding it during a drawdown |

**R-21.a** — An unanswered blocking item MUST NOT be resolved by picking a plausible default and
proceeding. Ask. The whole point of this table is that these are the questions where a wrong guess is
expensive and invisible.

---

## Appendix A — Configuration reference

All defaults are starting points. Values marked 🔒 are repo-only in live (R-11.2.b).

### A.1 Environment

| Variable | Type | Default | Notes |
|---|---|---|---|
| `ALPACA_ENV` | `paper`\|`live` | **none** | R-11.1.a. Missing → crash |
| `ATLAS_PHASE` | int 0–8 | none | Live requires ≥ 8 |
| `ATLAS_LIVE_CONFIRMED` | str | none | Must equal `yes-i-mean-it` for live |
| `ALPACA_API_KEY_ID` / `ALPACA_API_SECRET_KEY` | str | none | Per §16.3 |
| `ALPACA_DATA_FEED` | `sip`\|`iex` | `sip` | R-6.2.a |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY` | str | none | |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, `OPERATOR_PHONE` | str | none | |
| `RESEND_API_KEY`, `OPERATOR_EMAIL` | str | none | |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_ALLOWED_CHAT_ID` | str | none | R-13.6.b |

### A.2 Session

| Key | Default | Notes |
|---|---|---|
| `opening_range_minutes` | 15 | No entries before open + this |
| `no_new_entries_after` | 15:45 ET | R-12.4.a; calendar-derived |
| `force_flatten_at` | 15:55 ET | R-12.4.b; calendar-derived |
| `scan_at` / `rank_at` | 08:45 / 09:00 ET | |

### A.3 Stage A (§7.3)

`min_listing_days` 60 · `min_adv_usd` 20,000,000 · `min_prev_dollar_volume` 5,000,000 ·
`min_price` 5.00 · `max_price` 1000.00 · `max_spread_bps` 15 · `max_spread_bps_now` 25 ·
`min_trades_per_minute` 30 · `max_participation_pct` 0.01 · `min_atr_pct` 0.015 · `max_atr_pct` 0.15 ·
`expected_capture` 0.25 · `cost_multiple` 3.0 · `min_rvol` 1.5 · `min_premarket_dollar_volume` 500,000 ·
`min_gap_pct` 0.01 · `min_candidates` 15 · `max_candidates_hard` 400 · `max_per_sector` 12 ·
`scan_deadline_seconds` 180

### A.4 Labels and model (§9)

`pt_mult` 2.0 · `sl_mult` 1.0 · `holding_horizon_minutes` 120 · `vol_window_minutes` 60 ·
`cost_dead_zone_bps` 5 · `embargo_bars` 390 (1 session) · `stage_c_threshold` 0.60 ·
`regime_warning_threshold_bump` 0.05 · `drift_threshold_bump` 0.05 · `psi_alert` 0.25 ·
`shadow_mode_sessions` 10

### A.5 Risk 🔒 (§12.2)

`max_daily_loss_usd` **operator-set (O-2)** · `max_daily_loss_pct` 0.02 ·
`max_risk_per_trade_pct` 0.005 · `max_position_notional_usd` operator-set ·
`max_position_pct_of_equity` 0.20 · `max_concurrent_positions` 5 · `max_gross_exposure_pct` 1.00 ·
`max_net_exposure_pct` 0.60 · `max_sector_exposure_pct` 0.40 · `max_portfolio_heat_pct` 0.02 ·
`max_consecutive_losses` 4 · `max_entries_per_symbol_per_day` 1 · `max_orders_per_minute` 10 ·
`max_orders_per_day` 100 · `min_buying_power_buffer_usd` 1000 · `price_collar_pct` 0.05 ·
`max_quote_staleness_seconds` 10 · `max_risk_state_age_seconds` 5 ·
`max_spread_bps_execution` 25 · `pdt_check_enabled` **false** (R-2.4.a)

### A.6 Execution and resilience

`entry_limit_slippage_bps` 10 · `force_market_after_seconds` 60 · `reconcile_interval_seconds` 60 ·
`stop_placement_deadline_seconds` 5 · `stream_outage_halt_seconds` 30 · `pnl_tolerance_usd` 1.00 ·
`circuit_breaker_error_rate` 0.25 · `circuit_breaker_window_seconds` 60 · `latency_budget_ms` 250

### A.7 Kill switch and notifications

`halt_poll_interval_ms` 250 · `halt_slo_seconds` 10 · `halt_state_unreadable_halt_seconds` 5 ·
`halt_flatten_positions` true · `heartbeat_interval_seconds` 5 · `heartbeat_timeout_seconds` 30 ·
`drill_max_age_days` 8 · `max_notifications_per_hour` 10 · `quiet_hours` 22:00–07:00 ET

### A.8 Costs (§8.3) — verify every rate against `docs/SOURCES.md`

`sec_fee_rate` dated schedule · `taf_per_share` dated schedule · `taf_cap` dated ·
`borrow_bps_annual` per-symbol, default 300 · `misc_fee_bps` 0.1 · `base_slippage_bps` 2 ·
`impact_coefficient` 10 · `max_bar_participation` 0.10

---

## Appendix B — Domain primer and glossary

Read this if you have not traded professionally. The rest of the specification assumes it.

### B.1 How a trade actually costs money

A stock has a **bid** (highest price a buyer will pay) and an **ask** (lowest price a seller will
accept). The gap is the **spread**. To buy immediately you pay the ask; to sell immediately you accept
the bid. A round trip therefore costs you the spread **twice** even if the price never moves, plus fees
and the market impact of your own order.

If a stock is $50.00 bid / $50.05 ask, the spread is 5 cents = **10 basis points** (bps; 1 bp = 0.01%).
Buy and sell immediately and you are down ~20bps before anything happens. On $10,000 that is $20. If
your strategy's average winner is 30bps, costs eat two thirds of it.

**This arithmetic is the single most important thing in this document.** It is why Stage A filters on
spread (A11/A12), why rule A17 requires the expected move to clear costs several times over, why labels
are cost-adjusted (R-9.3.b), and why a backtest that fills at the mid price is worthless (R-8.3.b).

### B.2 Glossary

| Term | Meaning |
|---|---|
| **ADV** | Average daily volume, usually in dollars. Liquidity proxy |
| **ATR** | Average True Range — typical daily price movement. "ATR%" normalizes by price |
| **Basis point (bp)** | 0.01%. 100bps = 1% |
| **Bracket order** | An entry with an attached stop and profit target |
| **Buying power** | What the broker will let you deploy, ≥ cash for margin accounts |
| **Corporate action** | Split, dividend, merger, spin-off — events that change share count or price |
| **Drawdown** | Peak-to-trough decline in equity. Max drawdown is the worst such decline |
| **Easy to borrow (ETB)** | Shares readily available to short |
| **Flatten** | Close all positions to zero |
| **Gap** | Overnight price change between yesterday's close and today's open |
| **Halt** | Exchange-imposed trading pause. You cannot enter *or* exit |
| **Intraday** | Within one session. Atlas holds nothing overnight |
| **Marketable limit order** | A limit order priced through the touch — fills immediately like a market order but with a worst-case price |
| **Meta-labelling** | A second model deciding whether to act on the first model's signal |
| **NBBO** | National Best Bid and Offer — the consolidated best quote |
| **Opening range** | The high/low of the first N minutes. A common reference level |
| **Point-in-time (PIT)** | Data as it was known at a past moment, not as later restated |
| **Purging / embargo** | Removing training samples that overlap or sit adjacent to the test window |
| **Relative volume (RVOL)** | Today's volume vs. the typical volume at this time of day |
| **Sharpe ratio** | Return per unit of volatility, annualized. **Deflated Sharpe** corrects it for how many strategies you tried |
| **SIP** | Securities Information Processor — the consolidated tape, all exchanges |
| **Slippage** | Difference between the price you expected and the price you got |
| **Survivorship bias** | Testing on today's surviving companies, which excludes the failures |
| **Triple barrier** | Labelling by which of profit target / stop / time limit is hit first |
| **TIF** | Time in force. `day` orders expire at the close |
| **VWAP** | Volume-weighted average price. A common intraday benchmark |
| **Walk-forward** | Train on the past, test on the immediate future, roll forward. Repeat |

### B.3 Why the pipeline is split in three

- **Stage A (rules)** encodes things we **know** — a 40bps spread is untradeable at our size. Known
  facts belong in code, not in a loss function. Spending model capacity relearning them from noisy
  data is waste, and it makes the model's behaviour harder to reason about.
- **Stage B (ranker)** does the genuinely uncertain part: among 50 tradeable, interesting names, which
  are most likely to move our way? This is where learning earns its keep — cross-sectionally, within
  a day, where the comparison is apples to apples.
- **Stage C (gate)** answers a different question with different information: *right now*, given the
  spread, the volume, and what the market has done since the open, is this specific entry worth taking?
  Separating "what" from "whether" lets each model have a clean objective, and lets Stage C be tuned
  for precision (R-9.6.b) without distorting Stage B's ranking.

### B.4 Why the operator is in the loop every day

Not because the model needs approval to be correct, but because a 24-hour authorization ceiling
(R-3.4.b) bounds the damage from every unanticipated failure — a bad model, a data poisoning, a bug, a
compromised credential, a market regime the training data never contained. The worst case is one day's
authorized capital. An always-on system has no such bound, and every argument for removing the daily
step is an argument for removing that bound.

---

## Appendix C — Database schema outline

Indicative DDL. `db/migrations/` is authoritative.

```sql
-- ============ Reference ============
CREATE TABLE symbols (
  symbol            text PRIMARY KEY,
  name              text NOT NULL,
  exchange          text NOT NULL,
  asset_class       text NOT NULL,
  sector            text,
  listed_at         date,
  delisted_at       date,                    -- R-6.4.c: never delete
  created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE universe_snapshots (            -- R-6.4.b
  as_of             date NOT NULL,
  symbol            text NOT NULL REFERENCES symbols(symbol),
  tradable          boolean NOT NULL,
  shortable         boolean NOT NULL,
  easy_to_borrow    boolean NOT NULL,
  marginable        boolean NOT NULL,
  PRIMARY KEY (as_of, symbol)
);

CREATE TABLE corporate_actions (             -- R-6.4.a, R-6.4.d
  id                bigserial PRIMARY KEY,
  symbol            text NOT NULL,
  action_type       text NOT NULL,           -- split | dividend | merger | spinoff
  effective_at      date NOT NULL,           -- when it became true
  knowledge_at      timestamptz NOT NULL,    -- when WE learned it
  ratio             numeric(20,10),
  cash_amount       numeric(20,8),
  raw               jsonb NOT NULL
);
CREATE INDEX ON corporate_actions (symbol, effective_at, knowledge_at);

CREATE TABLE market_calendar (
  session_date      date PRIMARY KEY,
  is_trading_day    boolean NOT NULL,
  open_at           timestamptz,
  close_at          timestamptz,             -- half-days differ: R-5.4.c
  is_half_day       boolean NOT NULL DEFAULT false
);

-- ============ Market data ============
CREATE TABLE bars_daily (
  symbol            text NOT NULL,
  session_date      date NOT NULL,
  open              numeric(20,8) NOT NULL,  -- RAW, unadjusted: R-6.4.d
  high              numeric(20,8) NOT NULL,
  low               numeric(20,8) NOT NULL,
  close             numeric(20,8) NOT NULL,
  volume            bigint NOT NULL,
  vwap              numeric(20,8),
  trade_count       integer,
  ingested_at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (symbol, session_date),
  CONSTRAINT bar_sane CHECK (low <= open AND low <= close AND high >= open
                             AND high >= close AND low <= high AND volume >= 0)
) PARTITION BY RANGE (session_date);

CREATE TABLE bars_minute_hot (LIKE bars_daily INCLUDING ALL);  -- current day only, §6.3.1

CREATE TABLE bar_files (                     -- R-6.3.b
  id                bigserial PRIMARY KEY,
  storage_path      text NOT NULL UNIQUE,
  session_date      date NOT NULL,
  version           int  NOT NULL DEFAULT 1, -- R-6.3.a: corrections make new versions
  row_count         bigint NOT NULL,
  byte_size         bigint NOT NULL,
  content_hash      text NOT NULL,
  min_ts            timestamptz NOT NULL,
  max_ts            timestamptz NOT NULL,
  ingest_run_id     bigint NOT NULL,
  created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE data_quality_runs (             -- §6.7
  id                bigserial PRIMARY KEY,
  as_of             date NOT NULL,
  ran_at            timestamptz NOT NULL DEFAULT now(),
  result            text NOT NULL,           -- pass | warn | block
  checks            jsonb NOT NULL
);

-- ============ Pipeline ============
CREATE TABLE scan_runs (                     -- §7.5
  id                bigserial PRIMARY KEY,
  as_of             timestamptz NOT NULL,
  session_date      date NOT NULL,
  universe_size     int NOT NULL,
  tier_counts       jsonb NOT NULL,
  regime_warning    boolean NOT NULL DEFAULT false,
  duration_ms       int NOT NULL,
  data_feed         text NOT NULL,           -- R-6.2.b
  config_hash       text NOT NULL,
  git_sha           text NOT NULL,
  environment       text NOT NULL
);

CREATE TABLE scan_candidates (
  scan_run_id       bigint NOT NULL REFERENCES scan_runs(id),
  symbol            text NOT NULL,
  passed            boolean NOT NULL,
  rejected_by       text,                    -- R-7.1.b: first failing rule, e.g. 'A11'
  rank              int,
  stage_a_score     double precision,        -- R-7.4.a: the ML baseline
  features          jsonb NOT NULL,
  PRIMARY KEY (scan_run_id, symbol)
);

CREATE TABLE rank_runs (
  id                bigserial PRIMARY KEY,
  scan_run_id       bigint NOT NULL REFERENCES scan_runs(id),
  model_id          text NOT NULL,
  feature_set_version text NOT NULL,
  as_of             timestamptz NOT NULL,
  config_hash       text NOT NULL
);

CREATE TABLE rank_candidates (
  rank_run_id       bigint NOT NULL REFERENCES rank_runs(id),
  symbol            text NOT NULL,
  rank              int NOT NULL,
  score             double precision NOT NULL,
  selected          boolean NOT NULL,        -- the top 10
  shap              jsonb,                   -- R-9.5.e, for the explain view
  PRIMARY KEY (rank_run_id, symbol)
);

-- ============ Control plane ============
CREATE TABLE authorization_grants (          -- §13.1
  id                bigserial PRIMARY KEY,
  rank_run_id       bigint NOT NULL REFERENCES rank_runs(id),
  granted_at        timestamptz NOT NULL,
  expires_at        timestamptz NOT NULL,
  revoked_at        timestamptz,
  revoked_reason    text,
  symbols           text[] NOT NULL,         -- R-13.1.c: frozen at grant time
  max_capital_usd   numeric(20,2) NOT NULL,
  max_orders        int NOT NULL,
  sides_allowed     text[] NOT NULL,
  granted_by_method text NOT NULL,
  granted_from_ip   inet,
  mfa_verified_at   timestamptz NOT NULL,    -- R-13.1.e
  config_hash       text NOT NULL,
  model_ids         jsonb NOT NULL,
  environment       text NOT NULL,
  CONSTRAINT grant_max_24h CHECK (expires_at > granted_at
                                  AND expires_at <= granted_at + interval '24 hours'),  -- R-13.1.a
  CONSTRAINT grant_capital_positive CHECK (max_capital_usd > 0)
);

CREATE TABLE halt_state (                    -- R-13.2.c/d: single row, durable
  id                int PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  active            boolean NOT NULL,
  activated_at      timestamptz,
  activated_by      text,                    -- web | telegram | twilio | deadman | engine
  reason            text,
  cleared_at        timestamptz,
  cleared_by        text,
  updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE kill_switch_events (
  id                bigserial PRIMARY KEY,
  triggered_at      timestamptz NOT NULL,
  path              text NOT NULL,
  engine_halted_at  timestamptz,
  orders_cancelled_at timestamptz,
  positions_flat_at timestamptz,
  latency_ms        int,                     -- R-13.2.a: measured end to end
  was_drill         boolean NOT NULL DEFAULT false,
  positions_open    int NOT NULL,
  environment       text NOT NULL
);

CREATE TABLE kill_switch_drills (            -- §13.3
  id                bigserial PRIMARY KEY,
  ran_at            timestamptz NOT NULL,
  path              text NOT NULL,
  manual            boolean NOT NULL,
  latency_ms        int NOT NULL,
  passed            boolean NOT NULL,
  notes             text
);

CREATE TABLE engine_state (                  -- R-4.6.b
  id                bigserial PRIMARY KEY,
  state             text NOT NULL,
  entered_at        timestamptz NOT NULL,
  reason            text,
  session_date      date NOT NULL,
  git_sha           text NOT NULL,
  config_hash       text NOT NULL
);

CREATE TABLE heartbeats (                    -- R-13.2.f
  service           text PRIMARY KEY,
  beat_at           timestamptz NOT NULL,
  state             text
);

-- ============ Trading ============
CREATE TABLE order_intents (
  id                bigserial PRIMARY KEY,
  intent_id         text NOT NULL UNIQUE,
  rank_run_id       bigint REFERENCES rank_runs(id),
  grant_id          bigint REFERENCES authorization_grants(id),
  symbol            text NOT NULL,
  side              text NOT NULL,
  target_shares     bigint NOT NULL,
  order_type        text NOT NULL,
  limit_price       numeric(20,8),
  entry_reason      text NOT NULL,
  stage_c_probability double precision,
  created_at        timestamptz NOT NULL DEFAULT now(),
  correlation_id    text NOT NULL
);

CREATE TABLE risk_decisions (                -- R-10.1.b step 5, R-12.2.ae
  id                bigserial PRIMARY KEY,
  intent_id         text NOT NULL REFERENCES order_intents(intent_id),
  approved          boolean NOT NULL,
  rejected_by_rule  text,                    -- e.g. 'R-12.2.x'
  reason            text,
  reduced_from_shares bigint,                -- R-12.1.d
  risk_state        jsonb NOT NULL,          -- full state at decision time
  decided_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE orders (
  id                bigserial PRIMARY KEY,
  client_order_id   text NOT NULL UNIQUE,    -- R-10.5.a
  broker_order_id   text UNIQUE,
  intent_id         text NOT NULL REFERENCES order_intents(intent_id),
  symbol            text NOT NULL,
  side              text NOT NULL,
  qty               bigint NOT NULL,
  order_type        text NOT NULL,
  limit_price       numeric(20,8),
  stop_price        numeric(20,8),
  tif               text NOT NULL DEFAULT 'day',   -- R-10.4.e
  state             text NOT NULL,
  filled_qty        bigint NOT NULL DEFAULT 0,
  avg_fill_price    numeric(20,8),
  submitted_at      timestamptz,
  terminal_at       timestamptz,
  environment       text NOT NULL,
  correlation_id    text NOT NULL
);

CREATE TABLE order_events (                  -- R-10.3.a, append-only
  id                bigserial PRIMARY KEY,
  order_id          bigint NOT NULL REFERENCES orders(id),
  occurred_at       timestamptz NOT NULL,
  from_state        text,
  to_state          text NOT NULL,
  broker_payload    jsonb
);

CREATE TABLE fills (
  id                bigserial PRIMARY KEY,
  order_id          bigint NOT NULL REFERENCES orders(id),
  broker_fill_id    text UNIQUE,
  filled_at         timestamptz NOT NULL,
  qty               bigint NOT NULL,
  price             numeric(20,8) NOT NULL,
  fees              numeric(20,8) NOT NULL DEFAULT 0
);

CREATE TABLE fill_quality (                  -- R-8.3.e
  fill_id           bigint PRIMARY KEY REFERENCES fills(id),
  nbbo_at_decision  jsonb NOT NULL,
  nbbo_at_submit    jsonb NOT NULL,
  nbbo_at_fill      jsonb NOT NULL,
  modeled_price     numeric(20,8) NOT NULL,
  slippage_bps      double precision NOT NULL
);

CREATE TABLE positions (
  id                bigserial PRIMARY KEY,
  symbol            text NOT NULL,
  session_date      date NOT NULL,
  side              text NOT NULL,
  qty               bigint NOT NULL,
  avg_entry_price   numeric(20,8) NOT NULL,
  stop_price        numeric(20,8),
  target_price      numeric(20,8),
  opened_at         timestamptz NOT NULL,
  closed_at         timestamptz,
  realized_pnl      numeric(20,8),
  exit_reason       text,
  grant_id          bigint REFERENCES authorization_grants(id)
);

CREATE TABLE pnl_daily (                     -- R-10.6.c
  session_date      date PRIMARY KEY,
  starting_equity   numeric(20,2) NOT NULL,
  ending_equity     numeric(20,2) NOT NULL,
  realized_pnl      numeric(20,2) NOT NULL,
  gross_pnl         numeric(20,2) NOT NULL,
  total_costs       numeric(20,2) NOT NULL,
  trade_count       int NOT NULL,
  win_count         int NOT NULL,
  environment       text NOT NULL,
  discrepancy_usd   numeric(20,2) NOT NULL DEFAULT 0
);

-- ============ Models ============
CREATE TABLE models (
  model_id          text PRIMARY KEY,        -- content hash
  stage             text NOT NULL,           -- b | c
  created_at        timestamptz NOT NULL DEFAULT now(),
  feature_set_version text NOT NULL,
  data_feed         text NOT NULL,           -- R-6.2.b
  storage_path      text NOT NULL,
  manifest          jsonb NOT NULL,
  metrics           jsonb NOT NULL,
  trials_count      int NOT NULL             -- R-8.5.b, feeds DSR
);

CREATE TABLE model_promotions (              -- R-9.7.a
  id                bigserial PRIMARY KEY,
  model_id          text NOT NULL REFERENCES models(model_id),
  evaluated_at      timestamptz NOT NULL DEFAULT now(),
  gates             jsonb NOT NULL,          -- G1..G11 each pass/fail with values
  passed            boolean NOT NULL
);

CREATE TABLE model_activations (             -- R-9.8.c
  id                bigserial PRIMARY KEY,
  model_id          text NOT NULL REFERENCES models(model_id),
  stage             text NOT NULL,
  activated_at      timestamptz NOT NULL,
  deactivated_at    timestamptz,
  activated_by      text NOT NULL,
  environment       text NOT NULL
);

CREATE TABLE predictions (                   -- R-9.9.a
  id                bigserial PRIMARY KEY,
  rank_run_id       bigint REFERENCES rank_runs(id),
  symbol            text NOT NULL,
  model_id          text NOT NULL,
  predicted_at      timestamptz NOT NULL,
  features          jsonb NOT NULL,
  score             double precision NOT NULL,
  decision          text NOT NULL,
  realized_label    int,                     -- filled in when the label resolves
  realized_return   double precision,
  shadow            boolean NOT NULL DEFAULT false   -- R-9.8.e
);

-- ============ Audit ============
CREATE TABLE audit_log (                     -- R-3.7.a/b, §17.4
  id                bigserial PRIMARY KEY,
  occurred_at       timestamptz NOT NULL DEFAULT now(),
  actor             text NOT NULL,
  actor_detail      text,
  action            text NOT NULL,
  entity_type       text,
  entity_id         text,
  before            jsonb,
  after             jsonb,
  reason            text,
  correlation_id    text,
  request_ip        inet,
  environment       text NOT NULL,
  git_sha           text NOT NULL,
  config_hash       text NOT NULL
);

CREATE OR REPLACE FUNCTION audit_log_is_append_only() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'audit_log is append-only (R-3.7.b); % rejected', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_no_update BEFORE UPDATE ON audit_log
  FOR EACH STATEMENT EXECUTE FUNCTION audit_log_is_append_only();
CREATE TRIGGER audit_log_no_delete BEFORE DELETE ON audit_log
  FOR EACH STATEMENT EXECUTE FUNCTION audit_log_is_append_only();
```

**R-C.a** — Every table above MUST have RLS enabled (R-16.4.a). Migrations are forward-only; a
correction is a new migration, never an edit to a released one.

---

## Appendix D — Rule index

Rules are defined in their home sections; this is the lookup table.

| Rule | Subject |
|---|---|
| R-0.5.a | A MUST is never weakened to unblock a phase |
| R-1.2.a | Single tenant, permanently |
| R-2.4.a/b | PDT check config-gated, not deleted; confirm status before live |
| R-3.1.a–c | Live is Phase 8; `ALPACA_ENV` explicit; live creds only in prod Fly |
| R-3.2.a/b | One order path; 100% branch coverage on the governor |
| R-3.3.a–c | 10s halt SLO; weekly drill; three independent paths |
| R-3.4.a–c | Authorization required, ≤24h, never auto-renews |
| R-3.5.a/b | PIT correctness; shared feature code |
| R-3.6.a | Money is Decimal, never float |
| R-3.7.a/b | Audit row in the same transaction; append-only |
| R-3.8.a | No MCP under `services/` |
| R-4.2.a–c | Engine singleton; API never orders; engine always-on in session |
| R-4.3.a/b | Ports only in domain code; fakes shared with the backtester |
| R-4.4.a–c | Feature/rule code shared; parity test |
| R-4.6.a–c | HALTED reachable from anywhere; state persisted; restart winds down |
| R-5.4.a–c | UTC storage; NY only at display; calendar-derived sessions |
| R-5.5.a–c | Money newtypes; decimal context; strict mypy |
| R-5.7.a/b | Pinned deps; ADR to add one to core or risk |
| R-6.2.a–c | SIP feed; feed recorded with artifacts; rate limits and circuit breaker |
| R-6.3.a/b | Bars immutable, corrections versioned; manifests hashed |
| R-6.4.a–g | Knowledge time; universe snapshots; delistings kept; as-of adjustment; PIT filters; causal windows; bar alignment |
| R-6.5.a–c | REST for bulk ingest; gap backfill; halt on stream outage |
| R-6.6.a/b | Contracts at the boundary; bar invariants |
| R-6.7.a/b | BLOCK stops trading, no override; results surfaced |
| R-7.1.a/b | Stage A deterministic; rejection reasons recorded |
| R-7.3.a | Attention tier cannot relax eligibility |
| R-7.4.a–e | Baseline score persisted; weights not PnL-fit; thin days OK; regime warning; sector cap |
| R-7.5.a | Scan deadline |
| R-8.1.a/b | Pessimistic assumptions; reproducible manifests |
| R-8.2.a/b | Backtester runs engine code; simulated broker enforces real constraints |
| R-8.3.a–f | Dated fees; cross the spread; participation cap; no same-bar fill; calibration; latency |
| R-8.4.a | Walk-forward support |
| R-8.5.a/b | Net-of-cost headline; trial counting |
| R-9.1.a | Leakage suite blocks merge |
| R-9.2.a–e | Hypothesis per feature; cross-sectional; time-of-day; stationarity; parity test |
| R-9.3.a–e | Vol-scaled, cost-adjusted barriers; dead zone; stop-first ties; no overnight barrier |
| R-9.4.a–d | Concurrency; purged walk-forward + embargo; banned splitters; sample weights |
| R-9.5.a–e | Cross-sectional training; rank labels; constrained hyperparameters; full ranking; importances |
| R-9.6.a–e | Conditional training set; precision objective; calibrated sizing; zero-trade days OK; threshold bumps |
| R-9.7.a–c | Gates in code with no override; honest-failure gate; model cards |
| R-9.8.a–e | Immutable artifacts; startup verification; operator activation; rollback; shadow mode |
| R-9.9.a–c | Prediction logging; drift monitoring; performance circuit breaker |
| R-9.10.a–c | Same pipeline; trials counted; window documented |
| R-10.1.a–d | The single order path and its steps; no bypass; cancels too |
| R-10.2.a | Intent provenance |
| R-10.3.a/b | Locked transitions; broker is truth |
| R-10.4.a–e | Marketable limits; escalation; protective stop; tick/quantization; day TIF |
| R-10.5.a–c | Deterministic client order id; reconcile before retry; rejection taxonomy |
| R-10.6.a–c | Reconciliation cadence; discrepancy halts; broker-derived PnL |
| R-10.7.a/b | Exits match labels; no averaging down or re-entry |
| R-10.8.a | Stops + day TIF are the last line of defence |
| R-11.1.a–d | ALPACA_ENV enforcement, derivation, live confirmation, visibility |
| R-11.2.a–c | Documented config; risk limits repo-only; config hash recorded |
| R-12.1.a–d | Pure function; ordered rules; fail closed; may only reduce |
| R-12.2.a–ae | The rules themselves; rejections persisted |
| R-12.3.a–c | Risk-based sizing; bounded confidence scalar; no rounding up |
| R-12.4.a–d | No new entries; force flatten; overnight incident; calendar-derived |
| R-12.5.a/b | Halt semantics; narrow halt-exit exemption |
| R-12.6.a–d | Branch coverage; property invariants; mutation testing; change process |
| R-13.1.a–h | Grant constraints and the authorization screen |
| R-13.2.a–i | Halt SLO, three paths, dual delivery, fail closed, dead-man's switch, semantics, simplicity |
| R-13.3.a–d | Drill cadence, manual component, staleness blocks, SLO failure |
| R-13.4.a–e | Outbox; critical never throttled; environment labelled; escalation; quiet hours |
| R-13.5.a/b | Actionable content; exact money |
| R-13.6.a–i | Telegram + Twilio webhook authentication and hardening |
| R-14.1.a–d | Envelope; money as strings; idempotency keys; problem details with rule IDs |
| R-14.2.a/b | Halt route simplicity and SLO; API never orders directly |
| R-14.3.a | Halt indicator polls; unknown beats stale |
| R-15.1.a–c | Halt on every screen; two taps; five-second answers |
| R-15.2.a | Live mode unmistakable |
| R-15.4.a–d | Timezone labels; staleness marking; decimal rendering; chart conventions |
| R-15.5.a | Every decision explainable |
| R-15.6.a/b | Generated client; no business logic in the frontend |
| R-15.7.a/b | Cookie sessions; TOTP for sensitive actions |
| R-16.2.a–c | One account; MFA; service credentials |
| R-16.3.a–e | Secrets matrix; example file; scanning; revoke-first; log redaction |
| R-16.4.a–d | RLS; no direct DB from the browser; least privilege; tested backups |
| R-16.6.a/b | Pre-deploy checks; no live deploys mid-session |
| R-17.1.a–c | Structured logs; correlation ids; levels |
| R-17.2.a | Pages only for act-now conditions |
| R-17.3.a | Halt path traced |
| R-17.4.a–d | Audit schema, trigger, coverage, same-transaction |
| R-17.5.a | Daily report |
| R-18.2.a/b | Deterministic tests; never live in tests |
| R-18.3.a | Required fixture days |
| R-18.6.a | Architecture import contracts |
| R-18.7.a/b | No live creds in CI; gates not bypassable |
| R-19.1.a–d | MCP proof of concept; research uses; write it down; sources dated |
| R-19.2.a–c | Paper keys only; no literal secrets; separate paper account |
| R-19.3.a–c | No MCP in `services/`; REST for bulk ingest; provenance for pasted values |
| R-20.9.a–c | Minimum viable capital; supervised first session; a failed gate means no live |
| R-21.a | Do not guess a blocking open item |
| R-C.a | RLS everywhere; forward-only migrations |

---

## Appendix E — Cost and fill model reference

```
round_trip_cost_bps = 2 × spread_bps/2          # cross on entry and exit
                    + 2 × slippage_bps
                    + sec_fee_bps                # sell side only
                    + taf_bps                    # sell side only
                    + borrow_bps_prorated        # shorts
                    + misc_fee_bps

slippage_bps = base_slippage_bps
             + impact_coefficient × sqrt(order_shares / bar_volume)
             + urgency_premium

spread_bps = spread_model(price, adv, minute_volume, minutes_since_open)
```

**Worked example.** $50.00 stock, 8 bps spread, $10,000 position (200 shares), bar volume 40,000.

```
spread cost      = 8 bps                                   (4 bps each side, twice)
slippage         = 2 × (2 + 10 × sqrt(200/40000))          = 2 × (2 + 0.707) = 5.4 bps
SEC + TAF (sell) ≈ 0.3 bps
misc             = 0.1 bps
round trip       ≈ 13.8 bps ≈ $13.80 on $10,000
```

The trade must clear ~14bps before it earns anything. Rule A17 requires the expected move
(`ATR% × expected_capture`) to be at least `cost_multiple` = 3× that — here, ~41bps — which for a
$50 stock means an ATR of at least ~1.7%, consistent with the `min_atr_pct` default. The Stage A
thresholds and the cost model are two views of the same constraint, and they MUST be kept consistent:
changing one without the other silently admits trades that cannot pay for themselves.

---

## Appendix F — Runbooks

Expand each into `docs/RUNBOOKS.md` with exact commands during Phase 6.

| # | Situation | First action |
|---|---|---|
| **F.1** | **Emergency stop** | `/halt` to the Telegram bot. Do not open a browser first. Verify the confirmation message; if none arrives in 10s, text `HALT` to the Twilio number; if still nothing, log into Alpaca directly and close positions there |
| **F.2** | Engine unresponsive, positions open | Check heartbeat age in `/system`. Halt. Confirm positions at the broker, not in Atlas. Protective stops (R-10.4.c) and day TIF (R-10.4.e) bound the loss while you work |
| **F.3** | Reconciliation discrepancy | The engine has already halted (R-10.6.b). Do not resume. Compare Atlas orders against the broker's blotter, identify the missing or extra fill, write the incident, resume only after the cause is known |
| **F.4** | Data quality gate BLOCK | The engine will not trade (R-6.7.a). Read the failed check, fix the data, re-run the gate. Do not add an override |
| **F.5** | **Credential exposed** | Revoke at Alpaca **first**, then rotate, then investigate (R-16.3.d). Order matters |
| **F.6** | Drill failed or stale | Live authorization is blocked (R-13.3.c/d). Diagnose the path that failed, fix, re-drill, record |
| **F.7** | Model drift alert | Stage C threshold has already been raised automatically (R-9.9.b). Review the drifted features, decide whether to roll back (R-9.8.d) or retrain |
| **F.8** | Loss limit breached | The engine is winding down (R-12.2.f). Do not raise the limit. Review the day, write the incident, decide the next session's authorization with a clear head |
| **F.9** | Deploy to live | Run the pre-deploy check (R-16.6.a). Not during market hours with positions open (R-16.6.b) |
| **F.10** | Restore from backup | Quarterly rehearsal (R-16.4.d). Restore to a scratch project, verify row counts and `audit_log` integrity, never restore over production without a fresh dump first |

---

## Appendix G — A day, concretely

Illustrative. Account $50,000, `max_risk_per_trade_pct` 0.5%, `max_concurrent_positions` 5.

```
04:00  Nightly ingest finishes. 8,143 symbols in today's universe snapshot, 3 new delistings.
05:00  Data quality gate: PASS (minute coverage 99.6%, no duplicates, broker close check ±0 ticks).
08:00  Engine boots. Lease acquired. Model atlas-b-7f3a91 (Stage B), atlas-c-2d8e04 (Stage C) loaded;
       feature_set_version v11 matches. State → WARMUP.
08:45  Stage A. 8,143 → tier 1: 6,902 → tier 2: 1,284 → tier 3: 417 → attention: 96 survivors.
       Sector cap trims 4. Top 50 by stage_a_score written. Scan took 41s. No regime warning.
09:00  Stage B ranks the 50. Top 10 selected. Top name: CRWD, score 0.83; SHAP says rvol (3.1×) and
       pre-market dollar volume ($41M) dominate.
09:05  Notification: "PAPER · 10 candidates ready. Max loss if all stop out: $1,250 (2.5%). Authorize?"
09:12  Operator reviews, sets capital cap $25,000, long-only, grant expires at 16:00 ET today.
       TOTP entered. Grant #418 written; audit row in the same transaction.
09:30  Open. Engine subscribes to bars + quotes for the 10.
09:45  Opening range complete. CRWD trades above its 15-min high on 2.4× volume.
       Stage C: 0.71 > 0.60 threshold. confidence_scalar 0.78.
       Sizing: stop 1.1% away → risk/share $2.31 → risk budget $250 → 108 shares → × 0.78 → 84 shares.
       $17,640 notional. Governor: all 30 rules pass. Marketable limit at $210.21. Filled 84 @ $210.18.
       Protective stop placed 1.4s later at $207.87.
10:02  NVDA triggers. Governor rejects: R-12.2.x — spread 31bps > 25bps limit. No position.
       Visible in /orders with the plain-English reason.
11:15  CRWD hits the profit target. Exit filled. +$412 realized, −$29 costs. Net +$383.
13:40  Second entry (PANW) stops out. −$243.
15:45  WINDING_DOWN. No new entries.
15:55  One position open (SMCI). Force-flatten: marketable limit, filled on the first attempt.
16:00  Close. Reconcile against broker: 6 orders, 8 fills, zero discrepancies.
       pnl_daily: realized +$291, gross +$364, costs $73, 3 trades, 2 wins.
16:05  Daily report emailed. Tomorrow's readiness: data gate pending, drill age 3 days, model OK.
17:00  Minute bars archived to Parquet, hash verified, hot table truncated.
```

Note what is ordinary here: one rejected candidate, one loser, three trades total, a net of $291 on
$50,000 (0.58%), and costs at 20% of gross PnL. That last ratio is the number to watch. If it climbs
toward 50%, the strategy is working for the exchanges rather than the operator, and §8.5's cost
breakdown is what makes that visible before the equity curve does.

---

*End of specification. Questions that this document does not answer belong in §21, not in an
assumption.*
