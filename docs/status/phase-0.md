# Phase 0 — Foundations and proof of concept

- **Date:** 2026-09-16
- **Spec:** MASTER_SPEC §20.1
- **Verdict:** 🔴 **GATE 0 NOT PASSED — 3 of 5 acceptance criteria met.**

Two criteria are outstanding and both need the operator. Nothing in Phase 1
should start until they are closed.

---

## Acceptance criteria

| # | Criterion | Status |
|---|---|---|
| 1 | CI green: ruff, mypy `--strict`, pytest, secret scan, import-linter | 🟡 **Partial** — every check runs and is green locally; the gitleaks job has never executed (no runner in this environment) |
| 2 | A test proves the process exits non-zero when `ALPACA_ENV` is missing, empty, or invalid | ✅ **Met** |
| 3 | A paper order placed and cancelled through the MCP, with a write-up | 🔴 **Blocked** — no MCP server and no paper credentials in this environment |
| 4 | `docs/SOURCES.md` has entries for feed entitlement, fee rates, rate limits, PDT status | 🟡 **Partial** — all four have rows, but 4 are PROVISIONAL and 5 UNVERIFIED; no primary source was reachable |
| 5 | `.env.example` complete with no values (R-16.3.b) | ✅ **Met** |

---

## What was built

### Environment guard — R-11.1.a (criterion 2)

`libs/atlas_core/config/env.py` and `bootstrap.py`. No stdlib-external
dependencies, no I/O, imported first by every entrypoint.

- `ALPACA_ENV` must be exactly `paper` or `live`. **No default.**
- Values are deliberately **not** trimmed or case-folded. `" Live "` means a
  deployment config is not what someone thinks it is, and repairing it hides
  that. There is a test asserting the absence of a default argument, so the rule
  cannot be softened without a failing build.
- Live additionally requires `ATLAS_PHASE >= 8` and
  `ATLAS_LIVE_CONFIRMED=yes-i-mean-it` (R-11.1.c).
- Exit code is **78** (`EX_CONFIG`), distinct from a generic crash, so a restart
  loop is diagnosable without opening logs.
- Base URL and credential variable names are derived from the same enum in one
  place, and a test asserts paper and live never share a credential variable
  (R-11.1.b).

**56 tests.** Both entrypoints are launched as real subprocesses across the
missing case and nine invalid values, asserting exit code and message — the
criterion asks about the *process*, not a function that raises.

The model-promotion half of R-11.1.c is **not** enforced yet; it needs the
registry and arrives with Phase 4. Noted here so it is not assumed done.

### Domain foundations

`Money`, `Price`, `Quantity` (R-3.6.a / R-5.5.a). `float` is a `TypeError` at
construction. `Price × Quantity → Money`; `Money + Price` fails both statically
and at runtime. `Quantity` rejects fractional shares and `bool`. 18 tests.

`utc_now` / `ensure_utc` / `format_for_display` (R-5.4). Naive datetimes are
rejected; display is always timezone-labelled; a test parses the module's AST —
with docstrings stripped — to assert no hardcoded session times (R-5.4.c).

These are scaffolding rather than Phase 1 work, but every later phase needs
them, and adding the float ban after prices exist in the codebase is far more
expensive than before.

### Architecture contracts — R-18.6.a

Five import-linter contracts. **Each was negative-tested**: a deliberate
violation was introduced, the contract broke, the violation was removed.

| Contract | Rule |
|---|---|
| `atlas_core` must not import `services` | R-4.3.a |
| Only adapters may import vendor SDKs | R-4.3.a |
| No MCP client under `services` or `atlas_core` | R-3.8.a, R-19.3.a |
| The API must not import the engine's execution path | R-4.2.b |
| The risk governor imports nothing that does I/O | R-12.1.a |

### Guards that exist before the code they govern

Both were negative-tested the same way.

- **Single order path** (R-10.1.c): an AST walk over `services/` and `libs/` for
  calls to broker order methods outside `execution/submit.py`, plus a scan for
  bypass parameters (`force=True`, `bypass_risk`, `skip_risk`, `dry_run=False`).
- **Banned CV splitters** (R-9.4.c): `KFold`, `train_test_split`,
  `TimeSeriesSplit` and four others are already forbidden in `services/` and
  `libs/`.

The moment a second order path or a random split is *convenient* is the moment
it gets written. Banning them now costs nothing.

### Database — R-3.7.b proven, not asserted

Two migrations: `0001_audit_log.sql`, `0002_schema_migrations.sql`.

Applied against a real PostgreSQL 16 and exercised. The append-only trigger
rejects:

| Operation | Result |
|---|---|
| `UPDATE audit_log SET ...` | ❌ rejected |
| `DELETE FROM audit_log` | ❌ rejected |
| `DELETE FROM audit_log WHERE false` (zero rows) | ❌ rejected |
| `TRUNCATE audit_log` | ❌ rejected |
| `INSERT` | ✅ permitted |

`FOR EACH STATEMENT` rather than `FOR EACH ROW` is why the zero-row delete is
also refused. The connection used was the **superuser table owner** — anyone
holding the service role key is the owner, so a guard the owner could step
around would be no guard. RLS is enabled and forced on every table, checked by a
query over `pg_class` so a future migration cannot forget it.

A forward-only guard (`CHECKSUMS.txt`) fails if a released migration is edited
*or* if a new migration is not recorded. It runs without a database, so it is
never silently skipped.

> **One real bug was found and fixed here.** The first version of the checksum
> test built its lookup dictionary with the key and value reversed, so the
> comparison never ran and the test passed against a deliberately edited
> migration. It was caught by negative-testing the guard rather than by reading
> it. Every guard in this phase was negative-tested for that reason.

### CI — `.github/workflows/ci.yml`

Six jobs: `secrets` (gitleaks, full history), `quality` (ruff, format, mypy
`--strict`, import-linter, a grep for `type: ignore` outside `adapters/`),
`leakage` (its own job so a red X is unambiguous), `test` (+ the 100%-branch
risk-governor gate), `migrations` (Postgres 16 service), `frontend` (declared
now, activates when `web/` exists in Phase 7).

`make check` runs everything CI runs except the database job, so local green and
CI green mean the same thing.

### Deployment scaffolding

Fly configs for all three apps. The engine is pinned to
`max_machines_running = 1` and `auto_stop_machines = false` (R-4.2.a, R-4.2.c) —
though the real singleton enforcement is the Postgres advisory lock in Phase 5,
because a platform setting is something a person can change in a hurry.
Dockerfiles deliberately do **not** bake `ALPACA_ENV`, so an image built for
paper cannot be promoted to live by re-tagging it.

---

## Test totals

| Suite | Count |
|---|---|
| `tests/unit/test_env_enforcement.py` | 56 |
| `tests/unit/test_money.py` | 18 |
| `tests/unit/test_time.py` | 8 |
| `tests/unit/test_single_order_path.py` | 5 |
| `tests/unit/test_migration_hygiene.py` | 2 |
| `tests/leakage/test_banned_splitters.py` | 7 |
| `tests/integration/test_migrations.py` | 10 |
| **Total** | **106** (96 without a database) |

`ruff` clean · `ruff format` clean · `mypy --strict` clean across 32 files with
zero `type: ignore` in `libs/` or `services/` · 5/5 import contracts kept.

---

## What is blocking GATE 0

### B-1 · The MCP proof of concept (criterion 3) — operator action

R-19.1.a requires the POC before engine code. It cannot run here: no Alpaca MCP
server is attached, no paper credentials exist, and the network egress policy
blocks `alpaca.markets`.

`docs/research/2026-09-16-alpaca-mcp-poc.md` contains the full script — 20 steps
across account, order lifecycle, market data, reference data, and limits — with
a "why it matters" for each and a table of the **six specification assumptions it
tests**. Two of those are load-bearing:

- **Duplicate `client_order_id` is rejected.** If Alpaca does not reject it, the
  primary idempotency mechanism in R-10.5.a is gone and §10.5 needs redesigning
  before Phase 5.
- **Bar timestamps are bar-open.** If they are bar-close, every feature and label
  is off by one bar. This is silent and it makes backtests look better.

Neither should be taken from documentation. Both should be measured.

### B-2 · Primary-source verification (criterion 4)

`sec.gov`, `finra.org`, `docs.alpaca.markets`, and `alpaca.markets` are all
blocked by the environment's egress policy. Values were obtained from search
summaries and are marked **PROVISIONAL** — usable for design, not for live
(R-19.1.d).

One finding is worth surfacing now because it validates a design decision:

> The SEC Section 31 fee went from **$0.00 per million to $20.60 per million on
> 2026-04-04**. A backtest spanning that date using a single "current rate"
> constant would be wrong on one side of it. R-8.3.a's requirement that fees be
> a dated `effective_from → rate` schedule is not hypothetical — it is already
> load-bearing for any backtest covering 2026.

The FINRA TAF also changed, from $0.000166 to **$0.000195 per share** on
2026-01-01, cap $9.79.

**Resolution:** either open those four domains in the environment's network
policy, or have the operator read each primary source and record the value, date,
and their name in `docs/SOURCES.md`.

---

## Open items still needing the operator (§21)

| # | Question | Blocks |
|---|---|---|
| **O-1** | Is the SIP data feed budget approved? Provisionally $99/mo, 10k req/min | **Phase 1** |
| **O-2** | Total capital, and maximum acceptable loss per day and cumulative | **Phase 6**, hard-blocks Phase 8 G8 |
| **O-3** | Confirm the equities-only resolution (ADR-0002) | — |
| **O-5** | Long-only or long and short at launch? Long-only is a simpler, safer v1 | Phase 5 |
| **O-6** | Cash or margin account? | Phase 5 |
| **O-11** | Confirm funding happens through Alpaca directly — Atlas implements no money movement | Phase 0 |

Every risk limit in Appendix A.5 is currently a placeholder because **O-2** is
unanswered. They are placeholders in a config file, which is the right place for
them to be wrong, but they cannot stay that way past Phase 6.

---

## Recommendation

Hold at GATE 0. Close **B-1** and **B-2**, and answer **O-1** and **O-11**.

B-1 is the one that matters most: it is cheap, it takes perhaps an hour, and it
tests six assumptions that Phases 1 through 5 are built on. Discovering that bar
timestamps are bar-close during Phase 4 means regenerating every label and
retraining every model. Discovering it now means changing one constant.
