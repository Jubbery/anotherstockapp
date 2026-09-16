# Phase 1 — Data platform (in progress)

- **Date:** 2026-09-16
- **Spec:** MASTER_SPEC §20.2, §6
- **Verdict:** 🟡 **IN PROGRESS.** The point-in-time machinery, schema, and quality
  gate are built and tested. **No data has been ingested** — every acceptance
  criterion that requires real bars is blocked on network access.

> Started while 🔴 GATE 0 is still open, at the operator's direction. GATE 0's
> two blockers (B-1, the MCP proof of concept; B-2, primary-source verification)
> are **unchanged and still open** — see the "Gate 0 is still open" section.

---

## Acceptance criteria (§20.2)

| # | Criterion | Status |
|---|---|---|
| 1 | 10y daily + 3y minute bars ingested and verified | 🔴 **Blocked** — no network route to Alpaca |
| 2 | Universe snapshots for every date, including delisted symbols | 🟡 **Machinery built and tested; no data** |
| 3 | As-of adjustment demonstrated on three real splits | 🟡 **Demonstrated on a modelled split**, not yet on real data |
| 4 | Data quality gate runs nightly and blocks on corrupted input | 🟢 **Gate built, 27 tests**; the nightly runner needs the ingest |
| 5 | Bar alignment convention verified by test | 🟡 **Convention encoded and tested**; the vendor's actual convention is unconfirmed (B-1) |
| 6 | Ten symbol-days cross-checked against the MCP | 🔴 **Blocked** |
| 7 | Ingest is resumable — kill mid-run, resume from checkpoint | 🟡 **Schema supports it**; the runner is not written |

---

## What was built

### The as-of adjustment engine — R-6.4.d / R-6.4.e

`libs/atlas_core/pit/adjustment.py`. The core of Phase 1 and the thing that, if
wrong, quietly corrupts everything downstream.

Raw OHLCV is stored; adjusted series are computed at read time, as of a date.
Three windows govern whether a corporate action applies to a bar, and confusing
them is the whole hazard:

| Window | Getting it wrong means |
|---|---|
| `bar_date < effective_at` | A split on the bar's own date is already in its raw prices. Applying it again produces a 90% one-day crash that never happened — which a momentum feature reads as signal |
| `effective_at <= as_of` | A split after the vantage point has not happened yet. This is R-6.4.e exactly: a $200 stock that later split 10:1 was not a $20 stock at the time and must not be filtered as one |
| `knowledge_at <= cutoff` | A vendor backfill often delivers an action days after its ex-date. A backtest must be as ignorant as we were |

**12 leakage tests**, built around a modelled NVDA-style 10-for-1 split. The one
that states the property directly: the same bar yields `$1,210` viewed from
2026-06-09 and `$121` viewed from 2026-06-10.

Dividends are **off by default**, and that is a decision rather than an omission:
Atlas holds nothing overnight, so a dividend never touches realised PnL. It is
documented in the module, with a note that the default becomes wrong if the
holding rule ever changes.

### Survivorship — R-6.4.b / R-6.4.c

`libs/atlas_core/pit/universe.py`. Snapshots are immutable and retain symbols
that later delisted. `assert_retains_delistings` is a smoke alarm: a multi-month
span of snapshots containing zero delistings is the signature of a universe
rebuilt from today's asset list, and it fails loudly. **7 tests.**

### The future-ops guard — R-6.4.f

`tests/leakage/test_no_future_ops.py`. An AST walk banning `shift(-n)`,
`center=True`, `bfill`, and `fillna(method='bfill')` in feature, label, and
training code. Active before any of that code exists, because the cheapest time
to ban a one-character mistake is before anyone has a reason to make it.

It includes a **self-check** that plants all four violations in a synthetic
module and asserts the detector fires — every other test in the file asserts an
*absence*, and an absence assertion passes just as happily when the detector is
broken.

### The schema — 12 tables, applied and exercised

`db/migrations/0003_data_platform.sql`, `0004_bars_daily_partitions.sql`.
Applied against real PostgreSQL 16; **20 integration tests** exercise the
constraints rather than reading them:

| Refused by the database | Rule |
|---|---|
| `low > high`, close outside range, negative volume, zero low | R-6.6.b |
| A minute bar not on the minute grid (`14:31:30`) | R-6.4.g |
| A split with a null or zero ratio | adjustment would be undefined |
| A trading day missing its close time | R-5.4.c |
| A `session_date` outside every partition | parsing-bug catcher |
| Deleting a symbol that has snapshot history | R-6.4.c |
| A `data_quality_runs.result` outside pass/warn/block | R-6.7.a |

`bars_daily` is partitioned by year, 2015–2030, with **no default partition** —
a default would silently absorb a `session_date` of `2202` and the row would sit
there looking valid.

> **A real security defect was found here.** Row-level security is **not
> inherited by partitions**: `ALTER TABLE bars_daily ENABLE ROW LEVEL SECURITY`
> protects queries naming the parent, but `SELECT * FROM bars_daily_2026`
> bypasses it entirely. All sixteen partitions were unprotected. Caught by
> `test_row_level_security_is_enabled_on_every_table`, which walks `pg_class`
> rather than trusting the DDL — the test was written in Phase 0 against two
> tables and found the hole the moment partitions existed. Fixed in migration
> 0004; the check now pins it.

### The data quality gate — §6.7

`libs/atlas_core/quality/gate.py`. Twelve checks, pure functions of a metrics
snapshot, for the same reason the risk governor is pure: a gate that queries a
database mid-evaluation has a verdict that depends on when you asked.

Six BLOCK, six WARN. **27 tests**, including the three that matter most:

- **An empty universe blocks rather than passing.** Zero symbols with zero bars
  is not 100% coverage — it is a collector that returned nothing, and treating
  silence as approval is how a broken metrics job becomes a green light.
- **A gate that ran no checks blocks.**
- **There is no override.** Asserted against the module's own AST (docstrings
  stripped), so adding `override`, `force_pass`, `skip_gate` or `bypass` fails
  the build. Negative-tested by planting an `override` parameter.

### The market calendar — R-5.4.c / R-12.4.d

`libs/atlas_core/calendar/session.py`. Contains no session times of its own; it
is arithmetic over calendar rows. Every decision time is measured **backwards
from the real close**, which makes half-days correct without a special case.

The test that justifies the module: on 2026-11-27 (the day after Thanksgiving)
the close is 13:00 ET, so force-flatten lands at **12:55 ET, not 15:55**. A
hardcoded flatten would fire 2h55m after the market had already closed, on a day
Atlas is supposed to end flat. An unknown date raises rather than defaulting.
**18 tests.**

---

## Totals

| | |
|---|---|
| Tests | **213** (183 without a database) |
| New this phase | 107 |
| Leakage suite | 32 |
| `mypy --strict` | clean, 48 files, zero `type: ignore` in `libs/` or `services/` |
| Import contracts | 5/5 kept |
| Migrations | 4, all applied and constraint-tested |

Every guard added this phase was **negative-tested**: a deliberate violation was
introduced, the guard fired, the violation was removed. The adjustment engine was
broken by making it ignore `as_of` (the classic retroactive-adjustment bug) and
two leakage tests caught it.

---

## What is not built

Deliberately deferred, or blocked:

| Item | Why |
|---|---|
| Bulk historical ingest (R-6.5.a) | Needs network. The schema and checkpoint tables exist; the runner does not |
| Nightly ingest job (§6.5.2) | Same |
| Parquet archive + DuckDB reader (§6.3.2–3) | Needs real bars to be meaningful |
| `MarketDataPort` / `ReferenceDataPort` | Would be designed speculatively without the POC's answers on field names and pagination. §4.3 says ports arrive with the phase that needs them; writing them from documentation we cannot read is how they come out wrong |
| Stream gap detection (R-6.5.b) | Needs a stream |

---

## Gate 0 is still open

Neither blocker moved.

**B-1 — the MCP proof of concept.** The Alpaca MCP server is now attached to the
session, but **every call fails**. The environment's network egress policy denies
`paper-api.alpaca.markets` and `data.alpaca.markets` at the CONNECT layer:

```
connect_rejected: gateway answered 403 to CONNECT (policy denial)
  host: paper-api.alpaca.markets:443
  host: data.alpaca.markets:443
```

`alpaca.markets`, `docs.alpaca.markets`, `sec.gov` and `finra.org` are blocked
too, so B-2 is unchanged and all fee/feed values in `docs/SOURCES.md` remain
PROVISIONAL.

**This is an environment configuration, not a credential problem.** The fix is to
allow those hosts in the environment's network policy
([docs](https://code.claude.com/docs/en/claude-code-on-the-web)), or to run the
POC from a machine with open egress.

### One thing the blockage did yield

The MCP **tool schemas** are readable even though the calls fail, and they
corroborate three design assumptions — at documentation strength, not
observation strength:

| Schema evidence | Confirms |
|---|---|
| `get_stock_bars(adjustment=...)` defaults to `"raw"`, supports `split`/`dividend`/`all` | R-6.4.d is implementable: raw bars are retrievable |
| `get_stock_bars(asof=...)` — *"point-in-time symbol mapping, useful for backtesting with historical ticker changes"* | PIT ticker mapping exists. **This is a hazard the spec does not currently handle** — a symbol that was reused after a delisting would silently join two companies' histories |
| `get_stock_bars(limit=...)` 1–10,000; `feed` = `sip`/`iex`/`otc`/`boats` | Sizes the ingest batching (R-6.5.a); corroborates S-1 |

The ticker-change finding is worth acting on. It is **not** currently a numbered
rule, and `symbols.symbol` is the primary key throughout the schema — which
assumes a ticker identifies a company for all time. It does not.

---

## Recommendation

1. **Open the egress policy for Alpaca** (`paper-api.alpaca.markets`,
   `data.alpaca.markets`, `docs.alpaca.markets`) and run the POC. It closes
   GATE 0, unblocks ingest, and answers the six assumptions Phases 1–5 rest on.
2. **Answer O-1** (SIP feed budget). Ingest cannot start without knowing which
   feed it is ingesting — the feed is recorded per row and per artifact (R-6.2.b),
   and mixing them is a promotion blocker.
3. Decide on the **ticker-reuse** hazard above. My recommendation is a surrogate
   key on `symbols` plus an `asof` symbol-mapping table, which is a schema change
   that is cheap now and expensive after 10 years of bars are loaded.

Items 1 and 2 are both operator actions. Until then Phase 1 can go no further
than it has: everything remaining needs data.
