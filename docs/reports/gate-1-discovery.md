# Gate 1 discovery report — UX-002, DATA-001, OPS-005

## Outcome

The dashboard data map is committed. It identifies confirmed endpoints and
explicitly records the missing weekly aggregate and trend-delta sources.
Server-side appointment doctor/service filters, endpoint tests, and browser
error/retry states are present in the current branch.

## Skills used

- `frontend-design` — read before the UI work and applied to dashboard and
  admin hierarchy, spacing, typography, and responsive treatment.

## Files changed

- `docs/ux/dashboard-data-map.md`
- `apps/api/app/modules/appointments/routes.py`
- `apps/api/tests/test_appointment_commands.py`
- `apps/api/tests/test_website_routes.py`

## Commands and results

- `npm run lint:web` — passed with zero warnings after the navigation fixes.
- `npm run build:web` — passed.
- `apps/api/.venv/bin/python -m pytest -q` — 130 passed, 13 skipped.
- `APP_ENV=production PYTHONPATH=. apps/api/.venv/bin/python apps/api/scripts/seed_demo.py` — refused as required; `APP_ENV=local` seed script compiles successfully.

## Tenant negative-control continuation

The fault injection remains test-only in
`apps/web/tests/tenant-isolation.spec.ts`; no production route, API module, or
Docker image injects tenant data. The API settings layer additionally rejects
`BREAK_TENANT_ISOLATION=1` for `local`, `staging`, and `production`, while
allowing it only under `APP_ENV=test`.

- Normal tenant isolation assertion passes in the final Chromium suite.
- `tests/test_authorization.py` — 4 fault-injection configuration tests pass.
- `BREAK_TENANT_ISOLATION=1` is wired in `.github/workflows/ci.yml` as an
  expected-failure job.
- Local negative execution remains blocked before the assertion by the managed
  browser runtime; see `completion-audit.md` for the exact failure.

## Risks / deviations

The seed script still requires a local migrated PostgreSQL instance for a full
runtime insert/read verification. The MCP screenshot remains an external
desktop prerequisite. Optional charts remain intentionally omitted because the
map has no confirmed aggregate endpoint.
