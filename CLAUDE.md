# Project instructions

## Read the spec first

[`docs/MASTER_SPEC.md`](docs/MASTER_SPEC.md) is the source of truth for this repository. Read **Appendix B**
(domain primer — skip only if you have traded professionally), then **Sections 1–4**, then **§20** before
writing code. It uses MUST / SHOULD / MAY, numbered rules (`R-x.y.z`), and 🔴 HARD GATES between build
phases.

## Working agreements

- **Build the phases in order** (spec §20). Each has acceptance criteria. Stop at the gate, write
  `docs/status/phase-N.md`, and report status rather than running ahead. The engine is the interesting
  part and it is deliberately Phase 5 — it is worthless without a trustworthy backtester, which is
  worthless without clean point-in-time data.
- **Do not weaken a rule to make progress** (R-0.5.a). If a `MUST` blocks you, that is information.
  Raise it.
- **Deviations get an ADR** in `docs/decisions/`, numbered, explaining what changed and why.
- Answer the open items in §21 with the operator rather than guessing (R-21.a) — especially **O-1**
  (SIP data feed budget) and **O-2** (capital and maximum acceptable loss), which every risk limit
  depends on.
- Cite the rule ID in a comment wherever you enforce one. A grep for `R-12.2.x` must find both the
  rule and its enforcement.

## Safety-critical areas

Treat these with more care than ordinary application code. A bug here costs real money.

| Area | Rule |
|---|---|
| `services/engine/risk/` | 100% branch coverage, zero surviving mutants. Pure functions. No exceptions (R-12.6) |
| Order submission | Exactly one path, through the risk governor (R-10.1.b). Never call the broker elsewhere |
| `ALPACA_ENV` | Explicit, no default. Missing value crashes at startup (R-11.1.a) |
| Live credentials | Production `engine`/`api` only. Never in CI, `.env.example`, local dev, or MCP config (R-16.3.a) |
| Feature code | Imported by both training and live paths, never duplicated (R-4.4.a) |
| Kill switch | Three independent paths, 10s p99, weekly drill. Simplest code in the repo (R-13.2) |
| Authorization | Expires within 24h, never auto-renews, scoped to an explicit symbol list (R-3.4) |
| `audit_log` | Append-only. Enforced by trigger. Written in the same transaction as the change (R-3.7) |
| `tests/leakage/` | Blocks merge. These catch bugs that make results look *better* (R-9.1.a) |
| Inbound webhooks | Telegram secret token + single allowlisted `chat_id`; Twilio signature if enabled (§13.6) |

## Tooling

The Alpaca MCP server (`.mcp.json`, **paper keys only**) is a first-class part of Phases 0–4: run the
proof of concept through it before writing engine code, validate bar data before building the ingest
pipeline, sanity-check scanner output, and investigate what the model got wrong. Write down anything you
learn that informs a decision (R-19.1.c) — a chat is not a durable artifact.

Two boundaries: **bulk historical ingest uses the REST API**, not tool calls (same Alpaca data either way),
and the MCP MUST NOT appear anywhere in `services/` — the engine calls Alpaca through `BrokerPort` so order
paths stay deterministic, idempotent, and risk-checked. Same applies to every other MCP server and
connector (R-19.3.a).

## Conventions

- Python: `ruff`, `mypy --strict` on `services/` and `libs/`, `pytest`. Money is `Decimal`, never `float`.
- Timestamps: timezone-aware UTC in storage; `America/New_York` only at display, always labelled.
- Session boundaries come from the exchange calendar, never hardcoded — half-days exist (R-5.4.c).
- TypeScript: `strict: true`. The API client in `web/lib/api/` is generated from OpenAPI — do not hand-write it.
- Every write that changes money, position, or authorization state goes in a transaction that also writes
  an `audit_log` row.
