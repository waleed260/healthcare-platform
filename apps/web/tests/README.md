# Browser test coverage

All fixtures in this directory are synthetic and are intercepted at the browser boundary; no real patient data or production services are used.

- `booking-concurrency.spec.ts` verifies two simultaneous requests for one doctor/slot produce one booking and one clear `APPOINTMENT_CONFLICT` message.
- `tenant-isolation.spec.ts` verifies Clinic A staff cannot see Clinic B patient, appointment, or website records through the UI.
- `rbac-flows.spec.ts` exercises representative owner, manager, doctor, receptionist, and website-editor permissions.
- `core-workflow.spec.ts` covers onboarding completion, website publishing, public booking, schedule approval/check-in, and queue completion.

Run the complete browser suite from `apps/web`:

```bash
npm run test:e2e
```

Run only the critical release-gate specs:

```bash
npm run test:e2e -- booking-concurrency.spec.ts tenant-isolation.spec.ts rbac-flows.spec.ts core-workflow.spec.ts
```
