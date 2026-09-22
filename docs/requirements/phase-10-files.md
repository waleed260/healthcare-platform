# Phase 10 private files traceability

| Requirement | Evidence |
| --- | --- |
| Private patient-document metadata | `0010_private_files.py`, `patient_documents` with generated storage key, hash, retention, legal hold, archive, and scan status |
| Encrypted filename metadata | `0041_encrypt_private_document_metadata.py` and `app/modules/files/service.py`: new writes encrypt the original display filename; legacy rows are migrated by tenant-scoped jobs while retaining only a generic extension-based name for rolling compatibility |
| Scan/quarantine state | `file_scan_events`, pending-scan default, `app/modules/files/scanner.py`, magic-byte verification, clean-only signed-access command |
| Upload limits and allowlist | `app/modules/files/service.py`: PDF/JPEG/PNG only, extension matching, SHA-256 format, 20 MiB limit, generated keys |
| Streamed private upload | `POST /api/v1/patients/{patient_id}/documents/upload` validates actual bytes, digest, magic signature, size, and MIME before writing a mode-0600 private object |
| Private object adapter | `app/modules/files/storage.py` uses traversal-safe atomic writes under the configured private root, or the server-only Supabase Storage API when `STORAGE_BACKEND=supabase`; scan jobs can load objects through the same adapter |
| Tenant/object authorization | Forced RLS and composite patient/uploader FKs; all routes resolve session tenant, reapply the centralized CRM patient scope, and return scoped 404s |
| Signed access safety | Access tokens are HMAC-bound to document, user, expiry, and nonce; `document_access_events` and audit events record access without storage keys, signed URLs, or file contents |
| Authorized download | `GET /api/v1/documents/{document_id}/download` requires the authenticated user-bound short-lived token, clean scan state, tenant scope, and records a `downloaded` access event |
| Scan job lifecycle | Uploads enqueue an idempotent `document_scan` background job; `run_next_document_scan` claims with `SKIP LOCKED`, delegates to the signature scanner, and records bounded failure/retry state |

The patient-document collection endpoint is bounded by a signed cursor scoped to
the patient, defaults to 50 records, caps pages at 100, and returns
`meta.next_cursor` for continuation.

Route-level regression tests now prove quarantined and expired signed-download
requests fail closed; the PostgreSQL integration matrix still must exercise
cross-tenant document access and signed downloads, with a synthetic two-clinic
case now present in `test_tenant_isolation.py` but skipped when PostgreSQL URLs
are unavailable. Remaining Phase 10 work:
bucket/policy provisioning evidence, external scanner binding, and the full
cross-tenant integration run. The application
proxy, quota checks, archive audit, public-media pipeline, scan event API, and worker
scheduling are implemented; Supabase service credentials remain server-only.
