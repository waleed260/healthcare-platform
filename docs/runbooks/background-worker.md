# Background worker operations

The API queues tenant-scoped jobs in PostgreSQL. Run a worker with an explicit
clinic ID; do not build a worker that enumerates clinics using the application
runtime role. A trusted scheduler may launch one process per active clinic.

## Supported job types

- `document_scan` — validates private patient-document size, digest, and magic bytes.
- `website_media_scan` — validates private draft image objects before publishing.
- `export` — creates a short-lived private privacy/audit export.
- `retention_cleanup` — expires delivered exports and removes expired/revoked
  website preview tokens; it does not purge patient or audit records.
- `follow_up_overdue_notification` — creates privacy-safe in-app notifications.

## Run one pass or poll

```bash
cd apps/api
PYTHONPATH=. python -m app.worker \
  --clinic-id 00000000-0000-0000-0000-000000000001 \
  --job-type document_scan --once
```

Run `retention_cleanup` at least daily for each active clinic, after confirming
the deployment's approved retention policy. The cleanup retains export and
audit metadata while deleting only expired delivery objects and unusable
preview tokens.

For a long-running deployment, omit `--once` and supervise the process with
the platform service manager. Use a separate process/scheduler invocation for
each clinic and job type. Set the database URL and storage configuration through
the deployment secret manager; never put credentials in command arguments or
logs.

The worker claims jobs with `FOR UPDATE SKIP LOCKED`, uses bounded retries and
backoff, sets the same transaction-local tenant context as API requests, and
logs only job type and outcome. Monitor queued age, failed count, and scan/export
failure codes through the platform metrics endpoint. Exercise this runbook in
staging before production and retain the evidence with the release record.
