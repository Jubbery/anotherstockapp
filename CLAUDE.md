# Project instructions

## Read the spec first

[`docs/MASTER_SPEC.md`](docs/MASTER_SPEC.md) is the source of truth for this repository. Read Sections 1–4
and Appendix B before writing code. It uses MUST / SHOULD / MAY, numbered rules (`R-x.y.z`), and 🔴 HARD
GATES between build phases.

## Working agreements

- **Build the phases in order** (spec §20). Each has acceptance criteria. Stop at the gate and report status
  rather than running ahead. The engine is the interesting part and it is deliberately Phase 5 — it is
  worthless without a trustworthy backtester, which is worthless without clean point-in-time data.
- **Do not weaken a rule to make progress.** If a `MUST` blocks you, that is information. Raise it.
- **Deviations get an ADR** in `docs/decisions/`, numbered, explaining what changed and why.
- Answer the open items in §21 with the operator rather than guessing — especially **O-3** (equities vs
  options), which changes scope substantially.

## Safety-critical areas

Treat these with more care than ordinary application code. A bug here costs real money.

| Area | Rule |
|---|---|
| `services/engine/risk/` | 100% branch coverage. Pure functions. No exceptions |
| Order submission | Exactly one path, through the risk governor (R-10.1.b). Never call the broker elsewhere |
| `ALPACA_ENV` | Explicit, no default. Missing value crashes at startup (R-11.1.a) |
| Live credentials | Production `engine`/`api` only. Never in CI, `.env.example`, local dev, or MCP config |
| Feature code | Imported by both training and live paths, never duplicated (R-4.4.a) |
| `audit_log` | Append-only. Enforced by trigger |

## Tooling

The Alpaca MCP server (`.mcp.json`) is configured with **paper keys only** and is for interactive research
and debugging. It MUST NOT appear anywhere in `services/` — the engine calls Alpaca directly through
`BrokerPort` so that order paths stay deterministic, idempotent, and risk-checked. Same applies to every
other MCP server and connector (R-19.3.a).

## Conventions

- Python: `ruff`, `mypy --strict` on `services/`, `pytest`. Money is `Decimal`, never `float`.
- Timestamps: timezone-aware UTC in storage; `America/New_York` only at display, always labelled.
- TypeScript: `strict: true`. The API client in `web/lib/api/` is generated from OpenAPI — do not hand-write it.
- Every write that changes money, position, or authorization state goes in a transaction that also writes
  an `audit_log` row.
