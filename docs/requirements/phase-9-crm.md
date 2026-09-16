# Phase 9 CRM traceability

| Requirement | Evidence |
| --- | --- |
| CRM patient records and normalized search | `0006_appointments_engine.py`, `0009_crm_foundation.py`, `app/modules/crm/routes.py` |
| Duplicate control | `POST /api/v1/patients` returns `DUPLICATE_REVIEW_REQUIRED`; merge is a dedicated command with a reason and immutable `patient_merge_events` record |
| Tenant isolation | Composite tenant foreign keys and forced RLS on contacts, tags, patient tags, notes, consent, merge events; all routes set validated transaction context and subresource lookups return scoped 404s |
| Note visibility and lifecycle | Private doctor notes require `patient.private_note.read/write`; reception uses only clinic-visible notes; note updates use version locking and audit events |
| Archive behavior | Archive is an explicit command and excludes archived/merged patients from normal lists |
| Consent records | Dedicated read/manage endpoints, explicit versioned revocation, and append-only consent history rows |
| Patient history | `GET /api/v1/patients/{patient_id}/history` returns bounded appointment/merge timeline metadata without note bodies |

Branch-scoped CRM visibility now applies the explicit branch scope to patients
through their appointment branches, and linked doctor users are limited to
patients with appointments assigned to their doctor profile. Detail and
subresource commands use the same scoped object check and return a uniform 404
outside scope. The integration suite includes a synthetic branch-visibility
case; care-team relationships and clinic policy overrides remain intentionally
open because their data contract is not yet present in the repository.

Remaining Phase 9 work: care-team policy data model, audited exports, privacy
workflow integration, and the full two-clinic CRM isolation suite.

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
