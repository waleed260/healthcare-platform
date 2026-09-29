# Gate 3 backend slice — clinic lifecycle

## Scope

Slice A only: platform-admin approve, suspend, and reactivate commands. No UI
changes or unsupported platform-wide data surfaces are included in this gate.

## Implementation

- `POST /api/v1/admin/clinics/{clinic_id}/lifecycle`
- `ClinicLifecycleUpdate` requires `action`, a 10–1000 character `reason`, and
  `expected_version`.
- The existing MFA-backed `_platform` guard is used; no universal database
  bypass is added.
- Suspend revokes all clinic staff sessions and booking-management tokens.
  Existing session and public-booking checks also require an active clinic.
- Approve/reactivate set the clinic active; all commands clear archival state,
  increment the version, and emit a bounded global audit event with the reason.

## Evidence

- `tests/test_governance_schemas.py` and
  `tests/test_platform_admin_routes.py` — 9/9 targeted tests passed.
- Full API suite — 135 passed, 13 PostgreSQL-dependent skips in this shell.
- `admin-data-map.md` now records the lifecycle endpoint as confirmed.

## Slice B continuation — support access

- `GET /api/v1/admin/support-access`
- `POST /api/v1/admin/support-access`
- `POST /api/v1/admin/support-access/{access_id}/revoke`
- Creation requires a clinic, separate active requester and approver, requested
  permission codes, reason, and 1–60 minute expiry.
- Existing activation/exit routes and the database expiry constraint remain the
  enforcement boundary; expired contexts are rejected by session lookup.
- Platform audit metadata is global and bounded; no clinical content is
  returned by the platform list.

## Evidence

- Targeted lifecycle/support schema and route tests — 9/9 passed.
- Full API suite — 135 passed, 13 PostgreSQL-dependent skips.

## Slices C–D continuation — audit and privacy/export workflow lists

- `GET /api/v1/admin/audit` returns global, read-only, nonclinical audit fields.
- `GET /api/v1/admin/privacy-requests` and `GET /api/v1/admin/exports` iterate
  validated clinic contexts without adding a universal RLS bypass.
- Patient IDs, reasons, notes, metadata, and export payloads are excluded from
  platform responses.

## Evidence

- Targeted lifecycle/support/audit/privacy tests — 11/11 passed.
- Full API suite — 143 passed, 13 PostgreSQL-dependent skips.

The route evidence also covers the platform guard's non-admin `403` and
expired support activation's stable `409` response. PostgreSQL remains
required to prove the same invariants through real RLS, sessions, and expiry
timestamps.

## Pending

PostgreSQL integration must verify suspension against real staff sessions,
booking tokens, support-context expiry, and cross-tenant access. The platform
admin browser panel now consumes all confirmed slices, but hosted CI and the
Docker/PostgreSQL evidence remain pending.
