# Gate 4 report — TEST-001, TEN-004, RBAC-003

## Outcome

The four named Playwright specs and CI release-gate wiring exist, with one CI
retry and failure screenshots/video enabled. The focused release gate passed in
the latest completed run before the full-suite audit exposed CSP hydration
failures; commit `5026160` propagates the nonce through the Next request path,
and a new CI run is required to verify the complete suite.

## Commands and results

- `npx playwright test booking-concurrency.spec.ts tenant-isolation.spec.ts rbac-flows.spec.ts core-workflow.spec.ts` against the built production server — prior local run 16/16 passed across Chromium and mobile.
- Coverage includes booking conflict handling, onboarding → website publish → public booking → approval/check-in → queue consultation completion, tenant isolation, and five-role RBAC visibility/control checks.
- The Playwright web server now builds and starts the production app so the
  suite does not depend on Turbopack/HMR state.
- The post-fix core workflow and all five RBAC role cases passed in a fresh
  production-port rerun: 12/12 across Chromium and mobile. GitHub Actions run
  `36417907725` completed API/container successfully but the full web job
  failed: the focused gate passed, while the full smoke suite reported CSP
  hydration failures. Commit `5026160` restores request-side nonce propagation;
  final CI verification remains pending.

## Risks / deviations

The tenant test uses a deliberate Clinic A fixture and asserts Clinic B
patients, appointments, and website content are absent. The browser release
gate cannot be marked fully green until the post-`5026160` CI run completes.
