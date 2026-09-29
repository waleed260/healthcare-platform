# Gate 0 completion report — UX-001

## Outcome

The local Playwright MCP setup is documented in
`docs/runbooks/playwright-mcp.md`. The repository web app runs at
`http://127.0.0.1:3000` and the Playwright test configuration uses that URL.

## Files changed

- `docs/runbooks/playwright-mcp.md`
- `apps/web/playwright.config.ts` (existing release configuration)

## Commands and results

- `npm run dev:web` — local Next.js server ready on port 3000.
- `npm run build:web` — passed.
- Playwright MCP opened `http://127.0.0.1:3001/` and returned a screenshot:
  [`gate-0-landing-mcp.png`](screenshots/gate-0-landing-mcp.png).

## Current verification continuation

The API CI workflow now migrates PostgreSQL, runs the deterministic seed twice,
and verifies expected per-clinic counts plus clinic-A-only visibility through
the restricted runtime role using `infra/verify_seed.py`. The web CI workflow
also emits and uploads a mobile Lighthouse performance JSON artifact.

## Risks / deviations

The MCP browser used the local dev server on port 3001. The API was not running
in this shell, so protected-page screenshots intentionally show the product's
plain-language unavailable-workspace state rather than seeded data. The managed
shell has no Docker daemon and could not produce a local PostgreSQL or
Lighthouse result; CI is now wired to produce both artifacts.
