# Root Cause Report — Clinic CRM Workflow Issues

## Issue 1: Duplicate Services UI

**Root cause**: `branches/page.tsx` renders two SERVICES sections — one for doctor-level assignments (line 453) and one for branch-level assignments (line 479) — both using the identical "SERVICES" heading. Users see two identically-labeled sections and think it's a bug.

**Fix**: Renamed to "DOCTOR SERVICES" and "BRANCH SERVICES" respectively.

## Issue 2: Services Not Appearing in Book Appointment

**Root cause**: Two problems:
1. **Data setup**: Services must be assigned to BOTH the branch (`branch_services`) AND the doctor (`doctor_services`). The intersection of these sets is shown. If either is empty or they don't overlap, no services appear.
2. **Silent error**: The services and doctors API calls were in a single `Promise.all` with one catch handler. If services API failed, the error was reported as a doctors error, and the service list silently showed empty.

**Fix**: Separated API calls so each can fail independently. Added `serviceLoadError` state with distinct error message in Step 3.

## Issue 3: Time Slot Rejection Error

**Root cause**: `_validate_commit_time()` line 730 collapsed three distinct failure conditions (doctor on leave, time blocked, existing appointment overlap) into one generic "The selected time is no longer available" message. Users couldn't tell why their booking was rejected.

**Fix**: Split into three specific messages: "Doctor is on leave", "Time slot has been blocked", "Conflicts with existing appointment".

## Issue 4: Encounter List Shows Unbooked Patients

**Root cause**: By design — the encounter patient search queries all clinic patients via `/api/v1/patients?search=...`. Encounters can exist without appointments (walk-ins, emergencies). The perceived issue was actually Issue 5 — when navigating from a booked appointment, the patient wasn't pre-populated.

**Fix**: Issue 5's fix (already on disk) resolves this. No change needed to the global search behavior.

## Issue 5: Doctor and Type Not Inherited From Booking

**Root cause**: Already fixed prior to this session. Queue page "Start encounter" link passes `doctor_id`, `patient_id`, and `type` from the queue entry. Encounter form reads these URL params and pre-populates.

## Issue 6: Token Generation After Booking

**Root cause**: Already implemented prior to this session. Migration `0090_appointment_token_number` adds `token_number` to appointments. `create_internal_booking` generates a daily-sequential token. Frontend shows a Print Token screen in Step 6 after booking.

## Issue 7: Inventory Not Deducted

**Root cause**: **Missing feature**. The `encounter_update` endpoint saves `administered_treatments` and `medications` with `inventory_product_id` and `quantity` fields, but no code existed to adjust `inventory_stock`. Treatments were recorded but never triggered stock deduction.

**Fix**: Added `_apply_inventory_deltas()` to `encounters/routes.py`. On encounter update, when `administered_treatments` or `medications` change, the function:
1. Computes old vs new quantity maps per `inventory_product_id`
2. Applies the delta to `inventory_stock` (deducts for new/increased, restores for removed/decreased)
3. Records each adjustment in `inventory_adjustments`
4. Skips if encounter has no `branch_id`; clamps at 0 (doesn't block encounter save)

## Issue 8: Purchased Stock Not Appearing

**Root cause**: `purchase_receive()` in `purchase_routes.py` inserted/updated `inventory_stock` rows without setting `warehouse_id`. The `warehouse_id` column was added in migration 0087, but the receive flow wasn't updated. Stock rows had `warehouse_id = NULL`, making them invisible when users filtered by warehouse.

**Fix**: Added `warehouse_id` from the purchase order to the stock INSERT, UPDATE, and adjustment INSERT.
