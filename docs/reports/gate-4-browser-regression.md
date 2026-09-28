# Gate 4 report — TEST-001, TEN-004, RBAC-003

## Outcome

The four named Playwright specs and CI release-gate wiring exist, with one CI
retry and failure screenshots/video enabled.

## Commands and results

- `npx playwright test booking-concurrency.spec.ts tenant-isolation.spec.ts rbac-flows.spec.ts core-workflow.spec.ts` against the built production server — 2/16 passed (booking concurrency on Chromium and mobile); 14 failed in onboarding, queue, patients, and the core workflow.
- Production-server isolation confirms the booking fixture and its conflict
  assertion are healthy. Remaining failures are loading-state failures where
  the fixture-backed client collections do not reach their ready state.
- The Playwright web server now builds and starts the production app so the
  suite does not depend on Turbopack/HMR state.

## Risks / deviations

This gate is not complete. No green result or deliberate-break tenant test is
claimed until the clean dev-harness rerun passes.
