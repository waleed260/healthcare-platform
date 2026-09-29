# Completion audit — healthcare platform gates

This is an evidence audit of the current worktree. It intentionally separates
local evidence from checks that require hosted CI or PostgreSQL.

The human prerequisite commands are collected in
[`docs/runbooks/gate-0-unblock.md`](../runbooks/gate-0-unblock.md).
The single-command evidence collector is `scripts/verify-all.sh`; its host run
is pending.

| Requirement | Current evidence | Status |
| --- | --- | --- |
| CI API/container/web jobs green on `main` | No current GitHub run is reachable from this environment; the prior web failure predates the current fixes. | Pending hosted verification |
| PostgreSQL seed, reseed, counts, and runtime RLS visibility | `infra/verify_seed.py`, CI wiring, and native setup helper `scripts/dev/setup-local-postgres.sh` exist; no PostgreSQL service is available in this environment. | Host verification pending |
| Zero unexplained API skips | Local unit run: 143 passed, 13 integration skips without configured PostgreSQL URLs. | PostgreSQL run required |
| Web lint and TypeScript | `npm run lint:web` and `npx tsc --noEmit -p apps/web/tsconfig.json` pass. | Verified |
| Independent browser reseeding | `apps/web/tests/fixtures.ts` invokes the existing seed script when `PLAYWRIGHT_RESEED=1`; default mocked specs remain isolated. | Implemented, database execution pending |
| Mobile Lighthouse baseline | CI uploads `lighthouse-gate-0-mobile.json`; local Lighthouse package/network is unavailable. | CI-wired, artifact pending |
| Platform admin access, MFA/timeout, aggregate data boundary | Existing `_platform` guard uses MFA-capable sessions and active platform-admin identity; admin UI never requests clinical endpoints. | Locally verified |
| Admin lifecycle/support/audit/privacy platform-wide workflows | Lifecycle, support create/list/revoke, global audit, privacy workflow list, and export workflow list are implemented and unit-tested; real PostgreSQL cross-tenant/expiry verification remains pending. | Backend slices locally verified; integration pending |
| Landing motion and claims | Motion system, claims register, reduced-motion tests, axe checks, and 375/768/1440 coverage exist. | Locally verified; performance artifact pending |
| Dashboard functional polish | Existing responsive screenshots/reports and Chromium coverage are present; confirmed data gaps remain omitted. | Locally evidenced |
| Full browser regression | Final production-browser Chromium run passes 63/63, including admin, core workflow, RBAC, tenant isolation, CSP, and axe coverage. | Locally verified |
| Deliberately broken tenant assertion | `BREAK_TENANT_ISOLATION=1` fault switch is test-only; CI now runs the tenant spec and requires a non-zero result. Normal run passes locally. `PW_NO_SANDBOX=1` and an env-gated `PW_CHROMIUM_EXECUTABLE_PATH` override are supported, but this managed shell still terminates both bundled and system Chrome before the assertion runs. | Implemented, CI verification wired; local negative run blocked |
| Per-gate commits | Git index writes fail with `Read-only file system`; host commit instructions are in `docs/reports/pending-human.md`. | Host action pending |

## Local command evidence

- API: `PYTHONPATH=. .venv/bin/python -m pytest -q` from `apps/api` — 143
  passed, 13 skipped without PostgreSQL integration URLs.
- Web: lint and TypeScript pass.
- Browser: final Chromium 63/63; earlier shuffled Chromium baseline 60/60.
- Admin: platform access, clinic denial, lifecycle confirmation/submission,
  live support expiry, announcements, network clinical-data boundary, and
  retry behavior pass (5/5).
- Admin regression smoke: admin/admin-governance landmarks, CSP headers,
  governance approval flow, and axe checks pass (6/6).
- Admin screenshots generated and visually inspected at 375, 768, and 1440
  widths under `docs/reports/screenshots/admin-panel-*.png`.
- Final production-browser Chromium suite: 63/63 passed after the admin-panel
  rewrite and accessibility fixes.
- Diff hygiene: `git diff --check` passes.

## Negative-control command

`BREAK_TENANT_ISOLATION=1 npx playwright test --config=playwright.config.ts
tenant-isolation.spec.ts --project=chromium` is expected to exit non-zero because
the assertion detects the injected Clinic B patient. In this shell, Chromium
exited before test execution with `sandbox_host_linux.cc ... Operation not
permitted`; the same result occurs with `PW_NO_SANDBOX=1` and system Chrome
because the managed runtime terminates the browser process before the
assertion runs. This remains an external-environment verification item.
