# Fix Loop Log — Workflow Repair

## Session: 2026-11-06

### Issue 1 — FIXED
- **Change**: `branches/page.tsx` line 453: "SERVICES" → "DOCTOR SERVICES"; line 480: "SERVICES" → "BRANCH SERVICES"
- **Verify**: TypeScript passes (`npx tsc --noEmit` clean)

### Issue 2 — FIXED
- **Change**: `add-appointment-drawer.tsx` — added `serviceLoadError` state, separated service/doctor API calls, added red error message for service load failures in Step 3
- **Verify**: TypeScript passes

### Issue 3 — FIXED
- **Change**: `appointments/routes.py` line 730-731 — split single `if leave or blocked or busy` into three blocks with specific messages
- **Verify**: Python syntax check passes

### Issue 4 — NO CHANGE NEEDED
- Patient search is global by design. Issue 5 fix handles the booking-to-encounter flow.

### Issue 5 — ALREADY FIXED (on disk)
- Queue page already passes `doctor_id`, `patient_id`, `type` in encounter link
- Encounter form has fallback that fetches appointment details when only `appointment_id` is provided

### Issue 6 — ALREADY FIXED (on disk)
- Migration `0090_appointment_token_number` exists
- Backend generates daily-sequential token on staff booking
- Frontend Step 6 shows token with Print button

### Issue 7 — FIXED
- **Change**: `encounters/routes.py` — added `_inventory_qty_map()` and `_apply_inventory_deltas()` helpers. `encounter_update` now reads old treatments before update, computes inventory deltas, applies to `inventory_stock` and records in `inventory_adjustments`
- **Verify**: Python syntax check passes

### Issue 8 — FIXED
- **Change**: `purchase_routes.py` — added `warehouse_id` to PO query SELECT, stock INSERT, stock UPDATE (via COALESCE), and adjustment INSERT
- **Verify**: Python syntax check passes

### All Files Checked
- `npx tsc --noEmit`: Clean (0 errors)
- Python `ast.parse`: All 3 modified files pass
