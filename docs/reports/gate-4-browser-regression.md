# Gate 4 report — TEST-001, TEN-004, RBAC-003

## Outcome

The four named Playwright specs and CI release-gate wiring exist, with one CI
retry and failure screenshots/video enabled. The local production-browser
release gate is green after the nonce and accessibility fixes; hosted CI still
needs a fresh run against the current worktree.

## Skills used

- `frontend-design` — read before the landing and dashboard UI work; this gate
  verifies the resulting responsive and accessibility behavior.

## Commands and results

- `npx playwright test booking-concurrency.spec.ts tenant-isolation.spec.ts rbac-flows.spec.ts core-workflow.spec.ts` against the built production server — prior local run 16/16 passed across Chromium and mobile.
- Coverage includes booking conflict handling, onboarding → website publish → public booking → approval/check-in → queue consultation completion, tenant isolation, and five-role RBAC visibility/control checks.
- The Playwright web server now builds and starts the production app so the
  suite does not depend on Turbopack/HMR state.
- The post-fix core workflow and all five RBAC role cases passed in a fresh
  production-port rerun: 12/12 across Chromium and mobile. GitHub Actions run
  `36417907725` is retained as historical evidence only; it predates the final
  CSP/accessibility fixes and is not a current green result.

## Risks / deviations

The tenant test uses a deliberate Clinic A fixture and asserts Clinic B
patients, appointments, and website content are absent. The browser release
gate is locally green, but hosted CI and the Docker/Postgres seed verification
remain pending in this environment.

## Current continuation evidence

- `npm run lint:web` — passed with zero warnings after replacing the remaining
  internal dashboard anchors with an explicit, documented hash-link exception.
- `npx tsc --noEmit -p apps/web/tsconfig.json` — passed.
- `npm run build:web` — passed; `/admin` and `/admin/governance` are generated.
- `PYTHONPATH=. .venv/bin/python -m pytest -q` from `apps/api` — 143 passed,
  13 skipped.
- `npx playwright test --config=apps/web/playwright.config.ts smoke.spec.ts --project=chromium --grep 'renders /admin|renders /$|security headers'` — 3/3 passed.
- The new `landing.spec.ts` reduced-motion checks initially exposed React `#412`
  and blocked nonce-less inline RSC scripts. The root cause was the combination
  of static prerendering and the test server's standalone asset/runtime setup.
  The root layout is now dynamic for per-request CSP nonce rendering, and the
  browser harness validates the generated production app with its app server.
- `npx playwright test --config=apps/web/playwright.config.ts admin-panel.spec.ts landing.spec.ts --project=chromium` — 6/6 passed, including platform-admin access, clinic-staff denial, 375/768/1440 reduced-motion content visibility, no page errors, and axe contrast.
- Full Chromium regression after the CSP/accessibility fixes: `npx playwright test --config=apps/web/playwright.config.ts --project=chromium` — 63/63 passed, 0 failed, 0 skipped. This includes booking concurrency, core workflow, RBAC, smoke, admin, landing, and tenant-isolation specs.
- Browser specs now share an opt-in automatic fixture in
  `apps/web/tests/fixtures.ts`; setting `PLAYWRIGHT_RESEED=1` invokes the
  existing seed script before every test and requires `SEED_DATABASE_URL`.
  Default mocked runs remain database-independent.
- Shuffled CLI spec selection (`tenant-isolation`, `landing`, `admin-panel`,
  `rbac-flows`, `core-workflow`, `booking-concurrency`, `smoke`) also passed
  60/60 in the earlier Chromium baseline, confirming no run-order failure.
- The tenant assertion has a test-only `BREAK_TENANT_ISOLATION=1` fault switch;
  the normal test passes and the deliberately broken run is expected to fail,
  providing negative-control evidence without changing production isolation.
- `docker compose version` — unavailable on this workstation, so the
  Postgres-backed seed/reseed verification could not be run locally.
