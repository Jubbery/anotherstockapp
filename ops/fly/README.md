# Fly.io

Three apps (§4.2). Create them once, then deploy per app:

```bash
fly apps create atlas-engine
fly apps create atlas-api
fly apps create atlas-worker

fly deploy -c ops/fly/engine.fly.toml
```

## Secrets

Never in a `.toml` file, never in the repo (§16.3).

```bash
fly secrets set -a atlas-engine \
  ALPACA_PAPER_API_KEY_ID=... \
  ALPACA_PAPER_API_SECRET_KEY=... \
  SUPABASE_SERVICE_ROLE_KEY=...
```

**Live keys** (`ALPACA_LIVE_*`) are set only on the production `atlas-engine` and
`atlas-api` apps, and only at Phase 8 (R-3.1.c). Setting them anywhere else —
including a staging app, a dev machine, or `.mcp.json` — is the highest-impact
failure in the threat model (§16.1).

## Before any live deploy

R-16.6.a requires an automated, blocking pre-deploy check:

1. `ALPACA_ENV` matches the intended app.
2. The broker account endpoint confirms the account's paper/live nature (R-11.1.b).
3. The active model is promoted (§9.7).
4. The last kill-switch drill is within `drill_max_age_days` (R-13.3.c).
5. The data quality gate passed (§6.7).

And R-16.6.b: not during market hours with positions open, except a halt-path hotfix.
