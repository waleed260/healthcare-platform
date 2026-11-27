# Packages Section — Fix Summary

**Date:** 2026-11-27
**Branch:** `fix/packages-workflow` (off `origin/main` 071be45)
**Commits:** `b86cae7` (functional), `f1a3a7b` (drawer scrim), `3a493e2` (additional settings + 430px width) — all pushed
**0105 branch:** `fix/theme-instances-rls-nullif` untouched. No merge, no deploy.
**User file:** `PACKAGES_REPORTS_PROGRESS.md` untouched.

---

## 1. Root causes fixed

| # | Issue | Root cause | Fix |
|---|---|---|---|
| 1 | Selling failed | (a) Live DB was at `0094`; `patient_packages.idempotency_key` (migration `0096`) missing → every purchase 500 `UndefinedColumn`. (b) UI-created packages had **zero services**, so the sale was rejected. | Ran `alembic upgrade head` (`0094 → 0104`) + rebuilt `api/worker/migrate` images. `POST /packages` now writes definition **and** services in one transaction. |
| 2 | Deactivation failed | No transition guard; stale DB CHECK rejected `inactive`; repeat deactivate silently bumped the version. | Explicit `activate/deactivate/archive/unarchive` guards returning `INVALID_STATE` 409 with a clear message; inactive/archived sales rejected with the reason. |
| 3 | Deletion failed | **No DELETE endpoint existed.** | `DELETE /api/v1/packages/{id}`: hard delete only with **zero sales**, otherwise `409 PACKAGE_IN_USE` (“archive instead”). No cascade of patient/billing/sales history. |
| 4 | Form order / size | One long unordered form. | Six numbered sections (info → pricing → services → validity/usage → additional settings → review), compact two-column fields, drawer matching the booking drawer. |

Extra: patient/clinic checked on every sale; reuse of an idempotency key for a different sale → `409 IDEMPOTENCY_CONFLICT`; authorised overuse no longer violates `ck_patient_packages_used`.

---

## 2. Live API verification (real HTTP, synthetic clinic, test rows deleted)

| Action | Result |
|---|---|
| Create package with services | **201**, `total_sessions: 2` |
| Sell + invoice + cash payment | **201**, invoice `paid`, purchase active |
| Repeat same idempotency key | **201 same id**, **1** DB row |
| Edit (PUT) | **200** |
| Deactivate / reactivate | **200 / 200** |
| Repeat deactivate | **409** “already inactive” |
| Sell inactive | **409** “inactive … reactivate first” |
| Delete unsold | **200**, then GET **404** |
| Delete with sales | **409** `PACKAGE_IN_USE`, sale + invoice intact |
| Other clinic reads it | **404** (tenant isolation) |

## 3. Real browser run (Playwright + live backend, `localhost:3000`)

`PASS` page loads authenticated · drawer width **430** · sections **1…6** rendered · create via UI (POST 201) · sell via UI (POST 201, patient packages refreshed) · deactivate via UI (200, status shows inactive) · delete via UI blocked (DELETE 409, message shown). Screenshot: `/tmp/browser-packages.png`.

---

## 4. Changed files

- `apps/api/app/modules/packages/routes.py`
- `apps/api/app/modules/packages/schemas.py`
- `apps/api/tests/test_packages_workflow.py`
- `apps/web/app/(authenticated)/packages/page.tsx`
- `apps/web/app/globals.css`
- `packages/contracts/openapi.json`

---

## 5. Full verification (all run, nothing skipped)

| Check | Result |
|---|---|
| `bash scripts/verify-all.sh` | **passed** (evidence: `docs/reports/evidence/verify-all-20261127T191657Z.log`) |
| migrations | exit 0 |
| seed pass 1 + 2 + seed verifier | passed |
| runtime-role seed visibility | passed |
| API tests (`pytest`) | **421 passed**, exit 0 |
| `pytest tests/test_packages_workflow.py` | **3 passed** |
| `eslint . --max-warnings=0` | exit 0 |
| `tsc --noEmit` | exit 0 |
| `npm run build` | exit 0 |
| Playwright (all specs, shuffled) | **326 passed, 4 skipped, 0 failed** |
| tenant negative control | failed on injected data **as required** |
| RLS contract (`check_rls_contract.py`) | **PASSED — 113 forced tables and policies** |
| Lighthouse | skipped by design (not installed) |

---

## 6. Remaining, by design

1. **Merge + deploy** not done — needs explicit approval; Vercel still serves `main` until then.
2. Lighthouse performance evidence skipped because the binary is not installed (the script itself skips it by design).
3. Local app is running at **http://localhost:3000** against the Docker API on `:8000`.

---

## 7. Next action

Review and merge `fix/packages-workflow`, then redeploy the web app.
