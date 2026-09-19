# Object storage configuration

Development may use the traversal-safe local adapter. Production must use the
approved Supabase Storage buckets by setting `STORAGE_BACKEND=supabase` and
providing `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and the private/public
bucket names through the secret manager. The service-role key is server-only;
never expose it to the browser or use it in a `NEXT_PUBLIC_*` variable.

Patient-document display filenames are encrypted with `FIELD_ENCRYPTION_KEYS`.
Use the key-rotation runbook before retiring a key; a missing key makes private
document upload fail closed rather than writing plaintext metadata.

Create and policy the buckets before deploying the application. Keep patient
documents in a private bucket. Public website assets may use a public bucket
only after the application has made them clean and public in its own tenant-
scoped database transaction. The application still serves private documents
through its authenticated, user-bound proxy and does not return provider URLs.

Verify in staging with a synthetic document and image: upload, confirm
`pending_scan`, run the worker, confirm the scan event, verify unauthorized and
expired access fail, and verify a clean website asset is available only through
the verified hostname. Record bucket policy, object lifecycle, scanner result,
and deletion evidence before production approval.
