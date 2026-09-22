# Phase 9 CRM traceability

| Requirement | Evidence |
| --- | --- |
| CRM patient records and normalized search | `0006_appointments_engine.py`, `0009_crm_foundation.py`, `app/modules/crm/routes.py` |
| Duplicate control | `POST /api/v1/patients` returns `DUPLICATE_REVIEW_REQUIRED`; merge is a dedicated command with a reason and immutable `patient_merge_events` record |
| Tenant isolation | Composite tenant foreign keys and forced RLS on contacts, tags, patient tags, notes, consent, merge events; all routes set validated transaction context and subresource lookups return scoped 404s |
| Note visibility and lifecycle | `0040_crm_care_team_notes.py` adds the care-team relationship and fail-closed manager policy; care-team notes require explicit membership, private-note corrections remain author-only, and note updates use version locking and audit events |
| Archive behavior | Archive is an explicit command and excludes archived/merged patients from normal lists |
| Consent records | Dedicated read/manage endpoints, explicit versioned revocation, and append-only consent history rows |
| Patient history | `GET /api/v1/patients/{patient_id}/history` returns bounded appointment/merge timeline metadata without note bodies |

Branch-scoped CRM visibility applies the explicit branch scope to patients
through their appointment branches. Linked doctor users are limited to patients
with an appointment assigned to their doctor profile or an explicit care-team
relationship. Detail and subresource commands use the same scoped object check
and return a uniform 404 outside scope. The integration suite includes synthetic
branch-visibility and care-team/RLS cases.

The explicit care-team relationship is now backed by the RLS-protected
`patient_care_team` table. Doctor patient scope accepts a currently active
care-team relationship in addition to an assigned appointment; manager reading
of `care_team` notes remains denied until the versioned clinic policy explicitly
enables it. Care-team membership and policy changes are CSRF-protected and
audited. `test_crm_care_team_integration.py` verifies that the relationship
grants only its assigned doctor access and cannot be read or written across a
tenant context.

Remaining Phase 9 work is execution of the full two-clinic CRM isolation suite
against a local or hosted PostgreSQL instance.

Governance privacy requests and export target checks now reuse the CRM object
scope predicate, including linked-doctor and active care-team visibility rather
than branch scope alone. Export workers record a metadata-only `export.complete`
audit event using the requesting actor after the private artifact is written.
Hosted PostgreSQL execution is still required to prove the cross-tenant and
linked-doctor privacy/export matrix.

`test_privacy_requests_and_exports_are_isolated_and_foreign_targets_fail`
extends the synthetic two-clinic matrix to privacy requests and export jobs;
the local run is intentionally skipped without PostgreSQL, while CI/staging
must execute it with the runtime role and forced RLS enabled.

The protected `/privacy` workspace now integrates request creation, identity
verification evidence, explicit approval, execution, export-job status, and
short-lived one-time download access. It keeps patient IDs in server requests,
requires CSRF for every mutation, and makes deletion execution an explicit
operator action after the backend's identity and legal-hold gates.

The staff browser CRM directory is now available at `/patients`. It uses the
tenant-scoped patient list/search endpoint, exposes only basic directory fields,
and provides loading, empty, error/retry, refresh, and responsive tablet states.
Selecting a row opens `/patients/[patientId]`, which requests the authorized
patient detail, contacts, and visibility-filtered notes through separate
tenant-scoped endpoints and never attempts to bypass note permissions.
Patient creation now has an explicit `POST /api/v1/patients/duplicate-candidates`
review command. It stays within the authenticated clinic tenant, ranks exact
phone/email/date-of-birth/name matches, returns only bounded patient summary
fields, and audits the candidate count without storing submitted demographics.

The patient directory now uses a bounded, stable cursor (`limit` 1–100) signed
with the server session HMAC key. Cursors are namespace-bound and reject
tampering or reuse against another collection; the API returns `meta.next_cursor`
without changing the existing `data` array shape. The staff directory consumes
that cursor through an accessible append-only “Load more patients” state, with
loading and failure handling that preserves already loaded records.
