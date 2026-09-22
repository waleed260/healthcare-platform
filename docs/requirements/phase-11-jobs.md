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

Overdue follow-up notification discovery and expired-artifact cleanup process
deterministic batches of 500 rows per worker invocation. Remaining rows stay
eligible for the next explicit clinic worker run, preserving idempotency without
allowing a single transaction to grow with clinic history.

The integration suite now also covers end-to-end background-job isolation: a
worker running in one clinic can claim only that clinic's queued job under
forced RLS. The same suite covers public-host lifecycle isolation. The
PostgreSQL checks are skipped locally when integration URLs are not configured.

The checked-in `infra/scheduler/run-clinic-worker.sh` wrapper provides a
tenant-explicit, allowlisted one-pass command for managed cron/scheduler
registration without clinic discovery. Remaining Phase 11 work is deployment
registration for publish/backup schedules, browser-push delivery, provider
alert wiring, and deployment-backed timezone execution evidence.
