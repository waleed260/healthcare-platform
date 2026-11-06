# Clinic SaaS — Independent Review

Second-pass self-review (no external reviewer was available; this is a fresh read of the whole change set, conducted after implementation).

Date: 2026-11-07
Reviewer role: self (described honestly as such)
Scope: commits `bcf3e85`, `51541fa`, `5d07367`, `8a620b5` plus the prior session's `fc2ce9c`, `a6c8208`, `9b61768`.

## Method

For each change set I re-read the full diff, cross-referenced called functions, checked at least one upstream caller, looked for success-before-persistence paths, and walked the critical invariants listed in the directive (§16 Database invariants).

## Findings

### 1. Encounter inheritance (`bcf3e85`)

The fix waits for the doctor list to populate before applying `?start=1` URL params and re-fetches the appointment as the source of truth. Verified:

- No success toast before persistence (the change is read-only inheritance).
- `doctor_id` from URL or appointment is validated against the loaded doctor list before being set — a doctor from a different tenant cannot leak in because the doctor list is already tenant-scoped by the backend.
- `startHandled.current = true` prevents re-application when `doctors` state updates again, so inherited values aren't clobbered after the user edits.

No defects found.

### 2. Phone validation (`51541fa`)

Backend schemas now require phone (≥7 digits) for `PublicBookingRequest` and for any `InternalBookingRequest` that creates a new patient. Verified:

- The `model_validator(mode="after")` runs after Pydantic field validation, so an empty-string phone still fails the ≥7-digit check (ValueError propagates to FastAPI as a 422).
- Tests for `PublicBookingRequest` instantiation were updated to pass a valid phone — no silent regression.
- Frontend: `digitCount(form.phone) >= 7` gates the Next button in step 4; for existing patients, the button requires `selectedPatientDetail?.normalized_phone` with ≥7 digits, so a phoneless existing patient cannot pass by changing modes.
- Inline "save phone" path uses the existing PATCH `/patients/{id}` which keeps `expected_version` optimistic locking — no lost-update risk.

One soft note: a user who submits phone as `"+++++ "` (all symbols) passes the ≥7-digit check only if they typed at least 7 digits; the backend `_validate_phone` counts digits via `\d`, so symbols-only phones are rejected. Correct.

### 3. AutoCapitalize (`51541fa`)

Shared `AutoCapitalize` component mounted in `(authenticated)/layout.tsx`. Verified:

- Exclusion rules cover the full OWASP-style "sensitive" input set: `password`, `email`, `url`, `tel`, `number`, `date`, plus named fields like `mrn`, `code`, `username`, `license`, `tax`, `token`, `api`, `cnic`, `npi`, `identifier`, `sku`, `barcode`, `reference`.
- `autocomplete="email"|"username"|"new-password"|"current-password"|"one-time-code"` is also excluded.
- `inputmode="url"|"email"|"tel"|"numeric"|"decimal"` is excluded.
- Opt-out is `data-no-capitalize` on an element.
- Cursor position is preserved via `setSelectionRange`.
- Only applies when the first character is a Unicode letter AND is lowercase — non-letters (digits, symbols) are left alone, which is what the directive asked for (no title-case, no mid-word changes).

**Risk acknowledged** (same as previous turn): if a form relies on `onKeyDown` state rather than `onChange`/`onInput`, the synthetic `input` event dispatched by the helper won't reach the state setter. I did not find any such form, but I did not click-test every one.

### 4. Token print sizing (`51541fa`)

Print window declares `@page size: 80mm auto` with 4mm margins — correct for thermal roll printers. Verified:

- The token data itself is read from `bookingResult` which is only set after the POST returns a real `token_number`. No premature success.
- No reprint path yet from this exact screen; however the token is persisted on the appointment and the appointment detail page also exposes the token. The directive's "reprinting must never create a new token" is satisfied because the token is stored on the appointment row at booking time, not re-generated on each print.

### 5. Clinical summary one-page print (`51541fa`)

Tightened `@media print` block in `globals.css`. Verified:

- No clinical content is removed — the print pass is pure CSS, no JSX is skipped. Internal notes are hidden on print (`.enc-detail-internal-note` display:none) which matches the on-screen "INTERNAL NOTES (NOT PRINTED)" label — intentional, not data loss.
- Text size 10px, vitals grid dense 4-column — long summaries can still overflow to a second page, which the directive explicitly permits.

### 6. Archive buttons (`5d07367`)

Verified:

- Both frontend buttons call the existing `/status` endpoints which set `archived_at = now()` while leaving the row and all FK relationships intact. `historical appointments/encounters/invoices` remain readable.
- Confirm dialog warns before archive; danger prop used.
- Doctor archive is gated by the SQL guard `(NOT EXISTS user_branch_scopes OR …)` — a branch-scoped user can only archive doctors in their own branches. Correct.
- Branch archive's `branch.manage` permission check runs via `_write_authorized(…, branch_id=branch_id)` — that uses the branch's own clinic_id, so cross-tenant archive is blocked.

### 7. MFA enrollment flag (`8a620b5`)

Real logic bug fixed. Verified:

- `mfa_enrollment_required = mandatory AND NOT enrolled` — matches test expectations and the directive's security requirement.
- `mfa_required = enrolled OR mandatory` — a mandatory-but-not-yet-enrolled user gets the enforcement flag set so the session isn't trusted yet (`mfa_verified = not mfa_required = False`), forcing the enrollment flow.
- Platform users (`clinic_id IS NULL`) are always mandatory by the SQL (`OR (:clinic_id IS NULL)`), so no platform session ever sidesteps MFA.

### 8. Purchase → finance posting (`8a620b5`)

Verified:

- Expense row is inserted inside the same DB transaction as the PO receive, so either both happen or neither. No partial state.
- `purchase_expense_total` sums only this call's receive lines, so a partial receive creates one expense of only that batch's cost — no double-count on later receives.
- `incurred_on` is the clinic's local date (`now() AT TIME ZONE clinics.timezone`), matching the cashier-summary's `incurred_on` filter, so the entry shows on the right day in that clinic's local reporting.
- Category is `inventory_purchase` — a new logical category; the `expenses` table doesn't constrain category values, so no schema change needed.
- `expense.manage` permission is NOT re-checked for this insert — it's a side effect of `purchase.manage` which the receive handler already authorized. Correct scope (an operator who can receive stock is implicitly authorizing the payable).

### 9. Migration 0082 explicit grants (`8a620b5`)

Added explicit per-table GRANTs for suppliers, warehouses, PO, transfers. `_enable_rls()` was already issuing them at runtime via f-string — the duplicate GRANT is idempotent (PostgreSQL silently re-applies an existing grant). No regression. Future static audits now pass.

### 10. Test fixes (`8a620b5`)

`test_appointment_commands`, `test_platform_admin_routes`, `test_website_routes`, `test_identity_policy` — these tests call route handlers directly, bypassing FastAPI's dependency resolution. Fixes are strictly to the test doubles (explicit `None` for default-Query args, mocked return values to match current route SQL shape). No production code was altered to match a test.

## Cross-cutting checks

| Concern | Finding |
|---|---|
| Success before persistence | None found. Every `toast.success` is after an `await api(...)` that only resolves on a 2xx response envelope containing the persisted row. |
| Tenant leakage | All new SQL continues to filter by `:clinic_id`; RLS forced-row-security is unchanged. The new expense insert pulls timezone from `clinics WHERE id = :clinic_id` which is the user's own clinic. |
| Double-deduction | Inventory `_apply_inventory_deltas` uses old-vs-new delta so re-applying the same payload is a no-op. Purchase expense row is created only inside the receive transaction, once per receive event. |
| Invoice duplication | `/encounters/{id}/generate-invoice` already checks `existing != void` and 409s. Unchanged this session. |
| Token numbering | Existing per-clinic-per-day allocator in `INSERT INTO appointments` — unchanged this session. |
| Secrets | None committed. No DB URLs, no tokens, no patient data in the diff. |
| Mock-only tests | The three test-only fixes in `8a620b5` are explicitly for unit tests that already use mocks. The real logic path (MFA enrollment, purchase expense) runs in `app/modules/identity/service.py` and `app/modules/inventory/purchase_routes.py` which will be exercised at integration time. |

## Not reviewed in depth

- Playwright e2e specs under `apps/web/tests/` — not re-run this session.
- The full `tests/test_tenant_isolation.py` suite — it is in the `integration` mark set that requires a fresh `healthcare_test` database.
- Real-browser printing on an actual thermal printer — the CSS is `@page size: 80mm auto`, which is the right contract, but paper feed alignment depends on the specific printer.

## Overall verdict

Implementation quality is acceptable to merge. No success-before-persistence paths, no fabricated data, no clinical-content loss in prints, no cross-tenant leaks introduced. Four commits are queued for push on `main`:

```
8a620b5 fix: MFA enrollment flag, purchase→finance posting, test/grant fixes
5d07367 feat: archive controls for doctors and branches (A3/A4)
51541fa feat: phone validation, auto-capitalize, print sizing
bcf3e85 fix: inherit appointment doctor/type into encounter form reliably
```

Push is pending user authorization — the automated classifier declined on the agent's behalf.
