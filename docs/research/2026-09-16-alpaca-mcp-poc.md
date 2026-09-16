# Alpaca MCP proof of concept

- **Date opened:** 2026-09-16
- **Rule:** R-19.1.a — the POC runs through the MCP *before* any engine code is written
- **Status:** 🔴 **BLOCKED — not yet run.** See "Why this is blocked".

## Why this is blocked

R-19.1.a cannot be satisfied in the environment Phase 0 was built in:

1. **No Alpaca MCP server is attached to the session.** `.mcp.json` is written and
   committed, but the server itself is not running and this session has no
   mechanism to start one.
2. **No Alpaca paper credentials exist.** `ALPACA_MCP_PAPER_KEY_ID` and
   `ALPACA_MCP_PAPER_SECRET_KEY` are unset, and per R-16.3.a they are the
   operator's to create.
3. **The network egress policy blocks `alpaca.markets`**, so even a direct REST
   call could not substitute.

This is an operator action, not an engineering one. It is the single item
standing between Phase 0 and 🔴 GATE 0.

## What the operator needs to do

1. Create an Alpaca paper account **separate from the one the engine will use**
   (R-19.2.c — exploratory orders must not contaminate the Phase 7 soak record).
2. Export the keys:
   ```bash
   export ALPACA_MCP_PAPER_KEY_ID=...
   export ALPACA_MCP_PAPER_SECRET_KEY=...
   ```
   **Paper keys only** (R-19.2.a). Live keys in an MCP config would put live
   trading behind a natural-language interface with no risk governor.
3. Start a session with the Alpaca MCP attached and run the script below.
4. Record every answer in the "Findings" section and commit. A chat transcript is
   not a durable artifact (R-19.1.c).

## The script

Each step exists because something downstream depends on the answer. The
"why it matters" column is the part not to skip — an unexplained observation is
one nobody will act on.

### 1 · Account

| Step | Call | Why it matters |
|---|---|---|
| 1.1 | Get account | Confirms paper/live nature is machine-readable, which R-11.1.b's startup self-check depends on |
| 1.2 | Note every field name and type | `RiskState` (§12.1) is built from these; guessing field names costs a Phase 5 rewrite |
| 1.3 | Note `buying_power`, `cash`, `equity`, `daytrade_count` | R-12.2.t reads buying power from the broker, not from an Atlas estimate |
| 1.4 | Confirm whether `daytrade_count` is still returned | Direct evidence for **O-4 / S-6** (PDT status). If Alpaca still tracks it, the rule's status is not as settled as assumed |

### 2 · Order lifecycle

| Step | Call | Why it matters |
|---|---|---|
| 2.1 | Place a **marketable limit** buy, 1 share, liquid name, TIF `day` | R-10.4.a/e. Never a plain market order, even in the POC |
| 2.2 | Record every state the order passes through, with timestamps | The allowed-transition table in R-10.3.a must match reality, not the docs |
| 2.3 | Cancel it; record the terminal state | R-10.1.d — cancels go through their own governed path |
| 2.4 | Re-submit with the **same `client_order_id`** | **The idempotency assumption in R-10.5.a.** If Alpaca does *not* reject the duplicate, R-10.5.b's reconcile-before-retry loop is the only defence and needs redesigning. Confirm the exact error code |
| 2.5 | Submit with a deliberately malformed field | Feeds the rejection taxonomy in R-10.5.c |
| 2.6 | Submit oversized for buying power | Same. Distinguishes "insufficient buying power" from generic rejection |

### 3 · Market data

| Step | Call | Why it matters |
|---|---|---|
| 3.1 | Daily bars, 1 symbol, 30 days | Field names and types for `bars_daily` (Appendix C) |
| 3.2 | **Confirm the bar timestamp convention** — is a bar stamped 14:31Z the interval starting or ending at 14:31? | **R-6.4.g.** The most common lookahead bug in intraday systems. Verify by taking a 1-minute bar and checking its high/low against trades in each candidate window. Do not take the documentation's word for it |
| 3.3 | Minute bars across a session boundary | Are 09:30 and 16:00 bars present? Partial bars at the close? |
| 3.4 | Multi-symbol bars, ~100 symbols, note pagination | Sizes the ingest batching in R-6.5.a |
| 3.5 | Snapshot for 10 symbols; record bid/ask/spread | Calibrates the A11/A12 spread thresholds against reality |
| 3.6 | Same snapshot on **IEX vs SIP** if both available | Quantifies what R-6.2.a is buying. If the spreads differ materially, that is the O-1 business case in one table |
| 3.7 | Bars for a symbol that split recently | Are they adjusted? As of when? Directly tests the R-6.4.d assumption |
| 3.8 | Bars for a **delisted** symbol | If unavailable, R-6.4.b's universe snapshots must capture more at ingest time, because the history cannot be reconstructed later |

### 4 · Reference data

| Step | Call | Why it matters |
|---|---|---|
| 4.1 | Full asset list; count tradeable US equities | Validates the "~8,000" figure the whole pipeline is scaled to |
| 4.2 | Record `shortable`, `easy_to_borrow`, `marginable`, `fractionable` | Stage A rule A7, risk rule R-12.2.ac |
| 4.3 | Market calendar including a 2026 half-day | R-5.4.c / R-12.4.d. Confirm early closes are returned, not inferred |
| 4.4 | Corporate actions for a symbol with a recent split | Is there a knowledge/announcement date, or only an effective date? R-6.4.a needs the former; if it is absent, ingest must stamp `knowledge_at` itself |

### 5 · Limits

| Step | Call | Why it matters |
|---|---|---|
| 5.1 | Note rate-limit headers on any response | R-6.2.c's token bucket must be configured from the real limit, not S-2's provisional 10,000/min |
| 5.2 | Time a 100-symbol bar request | Feeds `scan_deadline_seconds` (R-7.5.a) |

## Findings

*(Empty. Fill in when the script is run — one subsection per numbered step, with
the raw observation and the conclusion drawn. Anything that contradicts an
assumption in the specification gets an ADR, not a quiet edit.)*

## Assumptions this POC is testing

Listed explicitly so that a failure is recognised as a failure rather than
absorbed. Each of these is currently **assumed**, and each has a specific
consequence if wrong:

| Assumption | Where it is relied on | If it is wrong |
|---|---|---|
| Duplicate `client_order_id` is rejected | R-10.5.a | The primary idempotency mechanism is gone; §10.5 needs redesign before Phase 5 |
| Bar timestamps are bar-**open** | R-6.4.g, and every feature window | Every label and feature is off by one bar. Silent, and it inflates backtests |
| Splits are adjusted, and we can get raw | R-6.4.d | PIT correctness needs a different mechanism; Phase 1 grows |
| Delisted symbols retain queryable history | R-6.4.b | Survivorship bias cannot be removed retroactively — ingest must snapshot from day one |
| The tradeable universe is ~8,000 names | §7, the whole funnel | Stage A thresholds re-scale |
| Corporate actions carry an announcement date | R-6.4.a | Ingest stamps `knowledge_at` at fetch time, which is coarser and must be documented |
