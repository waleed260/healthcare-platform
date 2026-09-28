# Gate 4 report — TEST-001, TEN-004, RBAC-003

## Outcome

The four named Playwright specs and CI release-gate wiring exist, with one CI
retry and failure screenshots/video enabled.

## Commands and results

- `npx playwright test booking-concurrency.spec.ts tenant-isolation.spec.ts rbac-flows.spec.ts core-workflow.spec.ts` — currently fails 16/16 in the managed dev harness.
- Failure evidence shows the booking/onboarding pages remain in their initial
  client loading state; the route fixtures receive no API request.
- Browser diagnostics identified and published a development CSP compatibility
  fix in `b400904`; a clean rerun is still required.

## Risks / deviations

This gate is not complete. No green result or deliberate-break tenant test is
claimed until the clean dev-harness rerun passes.
