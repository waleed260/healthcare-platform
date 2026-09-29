# Gate 4 report — platform admin panel

## Outcome

The `/admin` panel now presents the confirmed platform-admin surface: clinic
lifecycle controls, bounded support access, global audit events, privacy/export
workflow metadata, plans, announcements, and aggregate health. It keeps the
clinical boundary explicit and does not request patient, appointment, queue, or
operations endpoints.

Lifecycle actions require a confirmation dialog and a reason; support sessions
show a live countdown and provide explicit revoke control. Clinic versioning is
returned by the directory API and sent as `expected_version` for optimistic
concurrency protection.

## Current local evidence

- `npm run lint` from `apps/web` — passed.
- `npx tsc --noEmit -p tsconfig.json` from `apps/web` — passed.
- `PYTHONPATH=. .venv/bin/python -m pytest -q` from `apps/api` — 143 passed,
  13 PostgreSQL-dependent skips.
- `npx playwright test admin-panel.spec.ts --project=chromium` — 5/5 passed,
  including live support expiry and revoke removal.
- Screenshot artifacts generated and visually inspected at [375px](../reports/screenshots/admin-panel-375.png), [768px](../reports/screenshots/admin-panel-768.png), and [1440px](../reports/screenshots/admin-panel-1440.png).
- `npx playwright test smoke.spec.ts --project=chromium --grep 'admin|security headers|governance|axe'` — 6/6 passed.
- `npx playwright test --project=chromium` — 63/63 passed in the final
  production-browser run.
- `PW_NO_SANDBOX=1` and `PW_CHROMIUM_EXECUTABLE_PATH` are supported by the
  Playwright config for restricted environments; this managed shell still
  terminates both bundled and system Chrome before test execution, so the
  deliberately broken tenant run remains CI/host evidence.
- `git diff --check` — passed.

## Boundary and accessibility checks

The panel uses the existing MFA-backed platform-admin guard, retains the
nonce-based CSP, gives clinic staff an access-restricted view, and exposes only
aggregate/nonclinical workflow metadata. Admin and governance routes pass the
automated axe checks in the focused smoke run.

## Pending environment evidence

Docker/PostgreSQL integration, hosted CI, Lighthouse artifacts, and the
deliberately broken tenant-isolation browser run still require the environment
prerequisites recorded in the completion audit.
