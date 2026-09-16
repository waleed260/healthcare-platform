# Phase 5 catalog traceability

| Requirement | Evidence |
| --- | --- |
| Branch hours and holidays | `0004_catalog_onboarding_foundation.py`, `0022_holiday_scopes.py`, branch/full-day/time-range holiday APIs and scheduling integration |
| Doctor/service entities and tenant relationships | `doctor_profiles`, `services`, assignment tables with composite tenant FKs |
| Rooms/resources | `rooms`, `resources` with branch-scoped tenant FKs and migration `0028_catalog_resource_lifecycle.py` adding archive/version timestamps |
| Permission-protected catalog APIs | `app/modules/catalog/routes.py` (`GET/POST/PATCH /api/v1/services`, service status, branch CRUD/status, doctor CRUD/status, branch-service assignments, and schedule commands) |
| Resumable onboarding | `GET/POST /api/v1/clinic/onboarding` derives setup steps and persists audited completion via `0029_clinic_onboarding.py` |
| Strict input validation | `app/modules/catalog/schemas.py` and `tests/test_catalog_schemas.py` |
| RLS on catalog tables | Migration enables and forces RLS on every clinic-owned catalog table |

Branch list/create/update/status, multi-interval branch hours upsert, doctor CRUD/status, holiday deletion, room/resource CRUD/status, service update/status, branch-doctor assignment, and branch-service assignment/list/removal APIs are implemented in `app/modules/catalog/routes.py` with tenant permission, CSRF, strict schemas, optimistic version checks, and IANA timezone validation. Branch-specific commands pass the target `branch_id` into authorization so users with explicit branch scopes cannot manage another branch. Doctor-service assignment also rechecks the target doctor’s branch visibility in SQL, while clinic-wide users retain clinic-wide management. Public availability and booking now require the explicit branch-service assignment in addition to doctor/service eligibility; service duration and buffers remain stored as stable policy inputs. Onboarding is resumable through a derived checklist and completion timestamp, and `/onboarding` now exposes protected inline actions for the first branch, opening hours, care-team/service creation, and assignments. Remaining Phase 5 work: end-to-end database isolation coverage.
Room and resource lifecycle commands now support explicit active/archived status transitions scoped to their branch.

Branch and doctor collection reads use signed cursor pages with a default limit
of 50 and maximum of 100, preserving deterministic name/ID ordering within the
authenticated clinic context; branch collection reads reapply explicit branch
scope in SQL.

Branch-scoped room and resource listings use the same signed cursor contract,
with the branch authorization check applied before every page query.

Service listings and branch-assigned doctor/service listings are likewise
bounded and cursor-based, with stable name/ID ordering and branch authorization
on scoped collections.

Holiday reads use a signed cursor over date, an explicit time-present flag,
normalized time, and ID, preserving all-day-before-timed holiday ordering while
remaining branch-scope filtered.

Doctor update and status mutations enforce the caller’s branch scope in their
target-row predicates; unassigned or out-of-scope doctor IDs resolve as not found
to the scoped caller.

Top-level doctor listing applies the same assignment-based branch filter, so a
scoped user cannot discover care-team records outside authorized branches.

Migration `0035_inventory_and_hours.py` removes the one-interval-per-day
constraint and adds an explicit `interval_index`, preserving existing rows while
allowing multiple branch-hour intervals. It also adds the required
tenant-protected `doctor_rooms` relationship and the platform inventory tables
`access_tokens` and `system_announcements`.
