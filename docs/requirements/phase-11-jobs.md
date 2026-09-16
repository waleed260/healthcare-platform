# Phase 11 jobs traceability

| Requirement | Evidence |
| --- | --- |
| Database-backed jobs | `0011_background_jobs.py` creates tenant-scoped `background_jobs` with status, retry, lock, availability, and unique job keys; `claim_next_job`, `complete_job`, and `fail_job` implement serialized worker lifecycle; `app/worker.py` provides explicit-clinic polling and dispatch |
| Idempotent overdue processing | `app/modules/operations/jobs.py` claims one job per task/due timestamp and uses recipient/job uniqueness for notifications |
| Computed overdue state | Job selects due/contacted/booked tasks by `due_at`; it never rewrites the editable follow-up status to `overdue` |
| Privacy-safe notifications | Generated title/body contain no patient name, identifier, clinical detail, token, or signed URL |
| Tenant isolation | Background processing receives explicit `clinic_id` and sets the same transaction-local tenant context before queries/writes |

`GET /api/v1/admin/metrics` now reports aggregate queued/running/failed job
counts and oldest queued age alongside bounded HTTP latency and database-pool
gauges. It requires platform-admin context and emits no tenant identifiers or
patient content.

The integration suite now also covers end-to-end background-job isolation: a
worker running in one clinic can claim only that clinic's queued job under
forced RLS. The same suite covers public-host lifecycle isolation. The
PostgreSQL checks are skipped locally when integration URLs are not configured.

Remaining Phase 11 work: publish/backup scheduler binding, browser-push delivery,
provider alert wiring, and deployment-backed timezone execution evidence.
