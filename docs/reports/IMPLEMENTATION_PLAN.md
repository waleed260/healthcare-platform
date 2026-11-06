# Implementation Plan — Workflow Repair

## Phase Order

| Phase | Issues | Approach | Risk |
|-------|--------|----------|------|
| 1 — Quick UX fixes | 1, 3 | Label renames, message improvements | Low |
| 2 — Error handling | 2 | Separate API calls, add error state | Low |
| 3 — Stock tracking | 8 | Add warehouse_id to purchase receive | Low |
| 4 — Inventory deduction | 7 | Add delta-based stock adjustment on encounter update | Medium |
| 5 — Verification | All | Already-fixed items (4, 5, 6) — verify on disk | None |

## Changes Per Issue

### Issue 1 (1 file, 2 lines)
- `apps/web/app/(authenticated)/branches/page.tsx`: Rename "SERVICES" → "DOCTOR SERVICES" (doctor-level) and "BRANCH SERVICES" (branch-level)

### Issue 2 (1 file, ~15 lines)
- `apps/web/app/(authenticated)/_lib/add-appointment-drawer.tsx`: Add `serviceLoadError` state, separate service/doctor API calls, show service error message in Step 3

### Issue 3 (1 file, 4 lines)
- `apps/api/app/modules/appointments/routes.py`: Split generic error at line 730 into three specific messages for leave/blocked/busy

### Issues 4+5 (0 files — already fixed)
- Queue page already passes doctor_id, patient_id, type
- Encounter form has appointment-detail fallback

### Issue 6 (0 files — already fixed)
- Migration 0090 adds token_number to appointments
- Backend generates token on staff booking
- Frontend shows Print Token in Step 6

### Issue 7 (1 file, ~40 lines)
- `apps/api/app/modules/encounters/routes.py`: Add `_inventory_qty_map()` and `_apply_inventory_deltas()` helpers; call from `encounter_update` when treatments/medications change

### Issue 8 (1 file, ~8 lines)
- `apps/api/app/modules/inventory/purchase_routes.py`: Include `warehouse_id` in stock INSERT, UPDATE, and adjustment INSERT
