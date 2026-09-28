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
- API pytest — not runnable in the managed shell because Python test
  dependencies are not installed; CI installs `apps/api/requirements.txt`.

## Risks / deviations

The dev seed script and MCP screenshot remain open prerequisites for the full
Gate 1 exit. Optional charts remain intentionally omitted because the map has
no confirmed aggregate endpoint.
