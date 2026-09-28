# Gate 4 report — TEST-001, TEN-004, RBAC-003

## Outcome

The four named Playwright specs and CI release-gate wiring exist, with one CI
retry and failure screenshots/video enabled.

## Commands and results

- `npx playwright test booking-concurrency.spec.ts tenant-isolation.spec.ts rbac-flows.spec.ts core-workflow.spec.ts` against the built production server — 16/16 passed across Chromium and mobile.
- Coverage includes booking conflict handling, onboarding → website publish → public booking → approval/check-in → queue consultation completion, tenant isolation, and five-role RBAC visibility/control checks.
- The Playwright web server now builds and starts the production app so the
  suite does not depend on Turbopack/HMR state.
- The post-fix core workflow and all five RBAC role cases passed in a fresh
  production-port rerun: 12/12 across Chromium and mobile. The full 16/16 gate
  run remains recorded above; booking and tenant specs were unaffected by the
  response-parser change.

## Risks / deviations

The browser gate is green. The tenant test uses a deliberate Clinic A fixture
and asserts Clinic B patients, appointments, and website content are absent.
