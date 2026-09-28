# Playwright MCP local setup (UX-001)

This runbook is for local, synthetic-data browser work only. Do not point the
browser or database at production.

## Start the visible browser bridge

In a desktop terminal with a display:

```bash
npx @playwright/mcp@latest --port 8931 --browser chrome
```

Add the bridge to `~/.codex/config.toml`:

```toml
[mcp_servers.playwright]
url = "http://localhost:8931/mcp"
```

Older Playwright MCP versions expose the Server-Sent Events endpoint at
`http://localhost:8931/sse`; use that path only when `/mcp` is unavailable.

The app itself can be started with `npm run dev:web` and should be checked at
`http://127.0.0.1:3000`. Return screenshots from the browser bridge as the
Gate 0 exit evidence. Database checks belong in `psql` or pytest using the
local runtime role so row-level security is exercised; Playwright is not a
database client.

## Seed synthetic data

After applying migrations, run the dev-only seed with an admin/migrator
connection:

```bash
APP_ENV=local \
SEED_DATABASE_URL=postgresql://healthcare_migrator:healthcare_migrator_dev@localhost:5432/healthcare \
PYTHONPATH=apps/api python apps/api/scripts/seed_demo.py
```

The script refuses other environments and prints the synthetic password. Never
run it against production or use its credentials for real data.
