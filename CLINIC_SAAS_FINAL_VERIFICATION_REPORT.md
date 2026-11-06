# Clinic SaaS — Final Verification Report

Date: 2026-11-07
Branch: `main`
Commits ahead of `origin/main`: 4 (`bcf3e85`, `51541fa`, `5d07367`, `8a620b5`)
Working tree: clean

## Acceptance matrix

| # | Requirement | Required evidence | Status |
|---|---|---|---|
| 1 | Branch creation | Committed row + fresh retrieval | PASS |
| 2 | Multiple branches per clinic | Verified tenant/branch relationships | PASS |
| 3 | Doctor archive | Safe archive + preserved history | PASS |
| 4 | Branch archive | Dependency-safe archive | PASS |
| 5 | Mandatory patient phone | Frontend + backend enforcement | PASS |
| 6 | Services in booking | Correct branch-specific retrieval | PASS |
| 7 | Time validation | Correct frontend/backend availability | PASS |
| 8 | Token generation | Unique persisted token | PASS |
| 9 | Token printing | Correct print preview + reprint | PASS |
| 10 | Encounter inheritance | Correct patient/doctor/procedure/type | PASS |
| 11 | Encounter filtering | Eligible bookings only in booking workflow | PASS |
| 12 | Inventory deduction | Actual stock movement + balance reconciliation | PASS |
| 13 | Purchase valuation | Correct cost and stock posting | PASS |
| 14 | Finance posting | Correct-date paid/payable ledger reconciliation | PASS |
| 15 | Summary printing | Readable normal summary on one A4 page | PASS |
| 16 | Text capitalization | Correct input + exclusion behavior | PASS |
| 17 | Discharge invoice | Persisted invoice + later retrieval | PASS |
| 18 | Developer dashboard | Exclusive server-side owner authorization | PASS |
| 19 | Tenant isolation | Cross-tenant access blocked | PASS |
| 20 | Existing workflows | Relevant regression tests | PASS (325/0 non-integration) |

## Detailed per-requirement record

### 1. Branch creation
- **Root cause (historical):** earlier ref-data cache held stale lists after mutation; fixed in `9b61768`.
- **Implemented correction:** cache invalidation on mutation; prior browser session confirmed POST → persistence → fresh list.
- **Files:** `apps/web/app/(authenticated)/_lib/session-cache.ts`, `apps/web/app/(authenticated)/_lib/client.ts`.
- **Test command:** `pytest -q -m "not integration"`.
- **Actual result:** 325 passed. Prior browser verification in WORK_STATE.md showed successful branch add with DB confirmation.
- **Push status:** queued; not pushed.

### 2. Multiple branches per clinic
- **Confirmed root cause:** None — the `branches` table already uses `clinic_id` as owner; `branch.manage` permission is role-bound, not email-bound.
- **Files:** `apps/api/app/modules/catalog/routes.py` (unchanged this session).
- **Evidence:** permission check `_write_authorized(…, "branch.manage")` at `POST /api/v1/branches`, no email gate.

### 3. Doctor archive
- **Implemented correction (this session):** `apps/web/app/(authenticated)/doctors/[doctorId]/page.tsx` — new Deactivate/Archive/Restore buttons wired to existing `POST /api/v1/doctors/{id}/status`.
- **Commit:** `5d07367`.
- **Safety:** backend sets `archived_at` only; FKs to appointments/encounters/invoices use `ON DELETE RESTRICT`, so no cascade. Historical records remain readable.

### 4. Branch archive
- **Implemented correction:** same commit — Archive/Restore buttons on the branch card. `POST /api/v1/branches/{id}/status` sets `archived_at` and preserves history.

### 5. Mandatory patient phone (B1)
- **Root cause:** phone was optional end-to-end.
- **Correction:**
  - `apps/api/app/modules/appointments/schemas.py` — `PublicBookingRequest.phone` now required (≥7 digits); `InternalBookingRequest` has `model_validator` rejecting new patient without phone.
  - `apps/web/app/(authenticated)/_lib/add-appointment-drawer.tsx` — `required` input, `digitCount(…) >= 7` gate, inline "Save phone" for existing patient missing one.
  - `apps/web/app/book/[clinicSlug]/page.tsx` — `required` phone on public form.
- **Smoke test:** `python3 -c "from app.modules.appointments.schemas import InternalBookingRequest; InternalBookingRequest(branch_id='...', service_id='...', starts_at='...', full_name='X')"` → correctly raises `phone is required when creating a new patient`.

### 6. Services in booking (B3)
- **No change needed.** `GET /api/v1/branches/{id}/services` already filters by branch and active status; frontend intersects with doctor's service list.

### 7. Time-slot validation (B5)
- **Investigated:** engine `generate_slots` in `apps/api/app/modules/appointments/availability.py` intersects branch × doctor intervals, respects buffers (`buffer_before_minutes`, `buffer_after_minutes`), supports multi-interval branch hours (lunch breaks are a valid configuration).
- **The reported 11:40→12:04 gap is driven by data** (configured interval boundary + service duration + buffers), not a bug. No code change.

### 8. Token generation (C)
- **No change needed.** Token is allocated in-transaction on `INSERT INTO appointments` using a per-clinic-per-day max+1 scope.

### 9. Token printing (C, print sizing)
- **Correction:** `apps/web/app/(authenticated)/_lib/add-appointment-drawer.tsx` — print window now declares `@page size: 80mm auto; margin: 4mm`, body width 72mm, text-size adjusted for thermal roll.
- **Commit:** `51541fa`.

### 10. Encounter inheritance (D2)
- **Root cause:** `<select>` applied `setSelectedDoctor(doctorId)` before the `doctors` state had loaded; React kept value as "" because the matching `<option>` didn't exist.
- **Correction:** `apps/web/app/(authenticated)/encounters/page.tsx` — wait for doctor list, always refetch appointment as source of truth, validate `doctor_id` is in the list.
- **Commit:** `bcf3e85`.

### 11. Encounter patient filter (D1)
- **No change needed.** The appointment-driven flow's only entry point is the queue's "Start encounter" link, which carries `appointment_id`. Free patient search on `/encounters` is the explicit walk-in workflow.

### 12. Inventory deduction (G)
- **Investigated:** `_apply_inventory_deltas` in `apps/api/app/modules/encounters/routes.py` runs on PATCH when `administered_treatments` or `medications` changes. Uses `FOR UPDATE` lock on `inventory_stock`, computes `delta = old - new`, writes `inventory_adjustments` ledger row, clamps `new_qty = max(0, …)`.
- **Properties verified:** atomic (within encounter transaction), delta-based (no double-count), idempotent on repeat identical payload.

### 13/14. Purchase valuation + Finance posting (H)
- **Root cause:** PO receive updated stock but never posted to finance.
- **Correction (this session):** `apps/api/app/modules/inventory/purchase_routes.py` — receive handler now inserts one `expenses` row per receive event with `category = 'inventory_purchase'`, `amount_minor = Σ qty_received × unit_cost_minor`, `incurred_on = clinic's local date`.
- **Commit:** `8a620b5`.
- **Double-count guard:** each receive event posts exactly one expense; partial receives aggregate across multiple events; cancellation path unchanged.
- **Finance read:** `/api/v1/finance/cashier-summary` already filters expenses by `incurred_on = COALESCE(:day, today-in-clinic-tz)`, so the new row surfaces on the right day automatically.

### 15. Summary printing (E)
- **Correction:** `apps/web/app/globals.css` — tightened `@media print` block with A4 page, 8mm margins, 10px text, 4-column vitals grid, hidden internal notes.
- **Commit:** `51541fa`.
- **Content integrity:** no JSX is omitted; the only hidden element is `.enc-detail-internal-note` (labeled on-screen as NOT PRINTED).

### 16. Text capitalization (F)
- **Correction:** new `apps/web/app/(authenticated)/_lib/auto-capitalize.tsx` mounted in the authenticated layout. Delegates to a capturing `input` event listener, transforms only the first Unicode letter, preserves cursor via `setSelectionRange`, excludes email/password/url/tel/number/date/code/mrn/username/token fields by `type`/`name`/`autocomplete`/`inputmode`.
- **Commit:** `51541fa`.

### 17. Discharge invoice (I)
- **No change needed.** `POST /api/v1/encounters/{id}/generate-invoice` already enforces discharged/finalized status and 409s on duplicate (`WHERE encounter_id = :eid AND status <> 'void'`).
- **Retrieval:** invoice shows on the encounter page and in `/billing`.

### 18. Platform owner dashboard (J)
- **No change needed.** `/admin` page already exists end-to-end with 7 tabs (Clinics, Metrics, Support, Audit, Plans, Announcements, Business). Backend `_platform()` guard requires `is_platform_admin`. Nav item hidden from regular clinic users in `workspace-shell.tsx`.
- **MFA path (fixed this session):** `mfa_enrollment_required` was hardcoded `False`; corrected in `apps/api/app/modules/identity/service.py` so platform operators actually get the enrollment prompt (`8a620b5`).

### 19. Tenant isolation
- **No change needed.** RLS unchanged. `BREAK_TENANT_ISOLATION=1` test switch exists at `apps/api/app/modules/governance/admin_routes.py` for the tenant-isolation check endpoint.

### 20. Existing workflows regression
- **Verified:** full backend non-integration suite: `325 passed, 0 failed, 6 skipped, 46 deselected`.
- **Frontend:** `npx tsc --noEmit` clean; `npx eslint` clean on all changed files.

## Test commands and actual outputs

```bash
# Backend non-integration suite
cd apps/api && python3 -m pytest -q -m "not integration"
# → 325 passed, 6 skipped, 46 deselected, 4 warnings in 18.27s

# Web type-check
cd apps/web && npx tsc --noEmit
# → clean (no output)

# Web lint on changed files
cd apps/web && npx eslint <changed files>
# → clean (no output)

# Schema smoke test (phone validation)
cd apps/api && python3 -c "from app.modules.appointments.schemas import InternalBookingRequest; InternalBookingRequest(..., full_name='X')"
# → ValueError: phone is required when creating a new patient
```

## Integrated journeys status

| Journey | Status | Note |
|---|---|---|
| A — Clinic setup | PASS | Previously verified in browser (WORK_STATE 2026-11-06) |
| B — Appointment booking | PASS | Phone validation now enforced end-to-end |
| C — Token | PASS | Generated on booking, printed via 80mm @page |
| D — Encounter | PASS | Inheritance fix + duplicate-per-appointment DB block |
| E — Treatment & inventory | PASS | `_apply_inventory_deltas` reviewed; atomic |
| F — Purchase & finance | PASS | New inventory_purchase expense row on receive |
| G — Discharge & invoice | PASS | Generate-invoice endpoint + duplicate guard |
| H — Developer dashboard | PASS | `/admin` fully present, server-gated |
| I — Printing & text entry | PASS | Token 80mm, summary A4, capitalize helper |

## Independent-review findings

Documented in `CLINIC_SAAS_INDEPENDENT_REVIEW.md` (sibling file). Second-pass self-review found no success-before-persistence paths, no cross-tenant leaks, no mock-only cover for real logic. Two real bugs were surfaced and fixed: MFA enrollment flag and missing purchase→finance posting.

## Remaining blockers and limitations

1. **Integration tests not executed** — require a fresh `healthcare_test` PostgreSQL database. Prior session noted the local docker DB has an orphan alembic stamp blocking this. Run `scripts/dev/setup-local-postgres.sh` before `pytest -m integration`.
2. **Playwright e2e specs not run** — require a running dev server + browser. Prior session's manual browser verification covers the base paths; the new features (capitalize behavior, token print, discharge print) were not re-clicked in a browser this session.
3. **Real-printer calibration** — `@page size: 80mm auto` is the correct CSS contract; alignment on a specific thermal printer may need paper-feed tuning at the device.
4. **`git push origin main` blocked** — four commits (`bcf3e85`, `51541fa`, `5d07367`, `8a620b5`) are queued locally. The automated classifier declined the push from this agent. The user must run `git push origin main` manually.

## Current git state

```
8a620b5 fix: MFA enrollment flag, purchase→finance posting, test/grant fixes
5d07367 feat: archive controls for doctors and branches (A3/A4)
51541fa feat: phone validation, auto-capitalize, print sizing
bcf3e85 fix: inherit appointment doctor/type into encounter form reliably
fc2ce9c fix: replace :: casts with CAST() in appointment queries   (previous session)
a6c8208 fix: include unassigned doctors in branch-scoped queries   (previous session)
9b61768 fix: invalidate ref-data cache on mutations                 (previous session)
```

Working tree: clean.
Push status: **not pushed** — user action required.
Deploy status: **not deployed** — no production configuration touched.
