# Gate 1 discovery report — UX-002, DATA-001, OPS-005

## Outcome

The dashboard data map is committed. It identifies confirmed endpoints and
explicitly records the missing weekly aggregate and trend-delta sources.
Server-side appointment doctor/service filters, endpoint tests, and browser
error/retry states are present in the current branch.

## Files changed

- `docs/ux/dashboard-data-map.md`
- `apps/api/app/modules/appointments/routes.py`
- `apps/api/tests/test_appointment_commands.py`
- `apps/api/tests/test_website_routes.py`

## Commands and results

- `npm run lint:web` — passed with five existing Next navigation warnings.
- `npm run build:web` — passed.
- `apps/api/.venv/bin/python -m pytest -q` — 130 passed, 13 skipped.
- `APP_ENV=production PYTHONPATH=. apps/api/.venv/bin/python apps/api/scripts/seed_demo.py` — refused as required; `APP_ENV=local` seed script compiles successfully.

## Risks / deviations

The seed script still requires a local migrated PostgreSQL instance for a full
runtime insert/read verification. The MCP screenshot remains an external
desktop prerequisite. Optional charts remain intentionally omitted because the
map has no confirmed aggregate endpoint.
