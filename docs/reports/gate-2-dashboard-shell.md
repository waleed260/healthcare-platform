# Gate 2 report — UX-003, RBAC-002, OPS-005

## Outcome

Implemented the authenticated route group and shared workspace chrome for
dashboard, schedule, patients, queue, operations, website, and privacy. The
shell has a 240px dark desktop sidebar, permission-filtered links, shared
greeting/top bar, unread notification affordance, responsive collapse, and
keyboard-visible focus styling.

## Files changed

- `apps/web/app/(authenticated)/layout.tsx`
- `apps/web/app/(authenticated)/*/page.tsx`
- `apps/web/app/globals.css`
- `apps/web/proxy.ts`
- `apps/web/next.config.ts`

## Commands and evidence

- `npx tsc --noEmit -p apps/web/tsconfig.json` — passed.
- `npm run lint:web` — passed with five existing navigation warnings.
- `npm run build:web` — passed.
- Desktop dashboard screenshot — captured locally at 1440px; dark sidebar and
  shared top bar visible.
- Playwright MCP screenshots captured at 1920px, 1024px, and 768px:
  [`1920`](screenshots/gate-2-dashboard-1920-mcp.png),
  [`1024`](screenshots/gate-2-dashboard-1024-mcp.png), and
  [`768`](screenshots/gate-2-dashboard-768-mcp.png).
- Unavailable-backend state captured at 1920px:
  [`error state`](screenshots/gate-2-dashboard-error-state-mcp.png).

## Risks / deviations

The live authenticated dashboard still needs a migrated local database and
runtime login to verify seeded numbers. The existing page bodies still contain
legacy hidden chrome markup beneath the route-group shell; it is visually
suppressed and remains a cleanup target.
