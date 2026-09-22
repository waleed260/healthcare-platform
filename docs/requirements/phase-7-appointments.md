# Phase 7 appointment traceability

Scheduling CRUD is exposed under `/api/v1/scheduling` for availability rules,
leave blocks, blocked slots, and resource blocks. Commands require
`schedule.manage`, validate timezone-aware ordered intervals, apply branch scope
checks where applicable, require branch-doctor and branch-service assignments
for branch-specific rules/blocks, require active non-archived catalog objects,
and emit redacted audit events.

Scoped appointment list, detail, history, and assignment endpoints are exposed
under `/api/v1/appointments`; assignment uses a dedicated command with branch
doctor validation and `expected_version` locking.

The appointment collection is bounded by a signed, tenant-safe cursor. It
defaults to 50 records, accepts at most 100 per page, orders by `starts_at,
id`, reapplies branch scope in SQL even without a branch filter, and returns
`meta.next_cursor`; cursors are rejected when replayed with a different branch
or status filter.

Leave-block and resource-block scheduling collections use the same bounded
signed cursor pattern with stable start-time/ID ordering and clinic scope.

Availability-rule reads use a complete keyset cursor over branch, doctor,
weekday, start time, nullable service (zero-UUID sentinel), and ID, so recurring
rules with identical visible times remain deterministic.

Scheduling reads now reapply branch scopes in SQL: availability rules are
branch-filtered, clinic-wide leave remains visible while branch-specific leave
is restricted, and resource blocks join through their branch before returning.

Scheduling delete commands resolve the target branch under the tenant context
before CSRF/RBAC authorization, preventing branch-scoped users from deleting
objects in another branch by ID.

Booking-question support is implemented by `0026_booking_questions.py` and the
public appointment routes: active questions are service-scoped, required and
choice answers are validated, and accepted answers are persisted inside the
booking transaction without appearing in public management summaries.

| Requirement | Evidence |
| --- | --- |
| Occupancy math | `POST /api/v1/public/bookings` normalizes timestamps to UTC, stores duration/buffer policy snapshots and UTC occupancy boundaries; availability excludes branch/time-range holiday closures |
| Commit-time availability | Before patient creation or staff reschedule replacement, the service re-checks branch hours/breaks, doctor rules, holiday closures, leave, blocked slots, minimum notice, and the 90-day horizon; the exclusion constraint remains final conflict authority |
| Database conflict authority | `0006_appointments_engine.py` enables `btree_gist` and adds a doctor occupancy exclusion constraint |
| Idempotency | Tenant-scoped unique idempotency key, body hash mismatch response, and concurrent-conflict replay recovery |
| Tenant-safe public resolution | Booking resolves clinic by exact `X-Clinic-Slug` before setting transaction tenant context |
| Limited management token | Secret is returned once, only its HMAC is stored, and expiry is tied to appointment end |
| Lifecycle contract | `app/modules/appointments/state.py` encodes allowed transitions; dedicated approve, reject, and cancel command routes delegate to the same versioned, audited transition service |

Availability-rule evaluation is implemented in `0013_scheduling.py` and `app/modules/appointments/availability.py`; `GET /api/v1/public/availability` resolves the clinic, service, doctor, branch hours, holidays, appointments, leave, and blocked slots before returning UTC slots. Dedicated transition/reschedule commands are implemented in `0014_appointment_commands.py` and `app/modules/appointments/routes.py` with version locking, permission-specific guards, CSRF, replacement linking, audit writes, and target-appointment branch-scope checks. Reschedule replacements revalidate all booking rules and transition the superseded row to non-blocking inside the same transaction before the exclusion-checked insert, allowing safe moves while preserving rollback on failure. Public management summary, cancellation, and reschedule-request commands are implemented in `0016_public_booking_management.py` and use clinic resolution plus an independent hashed bearer secret without exposing patient or staff data; `0020_public_rate_limits.py` adds a serialized privacy-preserving request limiter. Completed staff reschedules now revoke the old token and issue a replacement token. DST fold behavior and token cross-tenant isolation now have regression coverage; remaining evidence gaps are PostgreSQL-backed execution of those isolation tests, queue operations, and production validation.

Availability conversion preserves both valid instants in a repeated DST hour,
skips nonexistent wall-clock starts, and resolves occupancy endpoints using the
candidate fold; regression coverage exercises both behaviors in
`tests/test_availability.py`.

Public catalog, availability, booking, and booking-question queries exclude
archived branches and services and inactive or archived doctors before exposing
or accepting a booking option.

The public booking surface now has cursor-bounded catalog and booking-question
endpoints at `GET /api/v1/public/catalog` and
`GET /api/v1/public/booking-questions`, plus a responsive browser flow at
`/book/[clinicSlug]`. The flow keeps clinic-local timezone labels visible,
uses the availability endpoint for selectable slots, submits the required
`Idempotency-Key` and clinic slug, and renders loading, empty, error, retry via
selection changes, submission, and confirmation states without exposing
internal patient or appointment IDs.
All public catalog, availability, booking-question, booking, and
booking-management resolution paths require an active, non-archived clinic.
