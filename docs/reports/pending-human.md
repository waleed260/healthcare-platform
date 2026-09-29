# Pending human actions

This file records host-only actions without treating optional tooling as a
release blocker.

| Item | Why Codex cannot finish it here | Exact host action |
| --- | --- | --- |
| Native PostgreSQL Gate 0 | The sandbox has no PostgreSQL service or `psql`; 13 integration tests remain skipped. | Run `./scripts/dev/setup-local-postgres.sh`, set the five printed connection URLs locally, then run `./scripts/verify-all.sh`. |
| Git commits and push | The sandbox cannot write `.git/index.lock`. | Review `git diff`, then run `git add -A && git commit -m "feat(admin): complete governance gates [REQ-9.3, REQ-14, REQ-16]" && git push`. |
| Reference dashboard image | The source image is not present in the workspace. | Copy the supplied reference image to `docs/ux/reference/dashboard_idea.jpeg`. |
| Browser negative control | The managed runtime terminates Chromium before the test assertion. | From a host terminal run `PW_NO_SANDBOX=1 BREAK_TENANT_ISOLATION=1 npx playwright test tenant-isolation.spec.ts --project=chromium` and retain the expected assertion failure output. |
