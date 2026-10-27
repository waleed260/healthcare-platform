# Background Jobs Audit

## Job Execution Architecture

**Queue mechanism**: `background_jobs` table with `FOR UPDATE SKIP LOCKED` claiming (`operations/jobs.py:29-39`).

**Claim flow**: `claim_next_job()` → `SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1` → `UPDATE status='running', locked_at=now()` → handler executes → `complete_job()` or `fail_job()`.

**Retry**: Exponential backoff via `retry_delay_seconds()` — `2^(attempts-1)` seconds, max 3600s. Max 5 attempts before permanent `failed` status.

**Stale recovery**: Jobs with `status='running' AND locked_at < now - 5 min` are reclaimed. This handles process crashes and Render spin-down.

**Concurrency safety**: `SKIP LOCKED` prevents duplicate claiming across multiple processes. **CONFIRMED SAFE for queue-based jobs.**

---

## Job-by-Job Analysis

### 1. `patient_media_scan`

| Field | Value |
|-------|-------|
| Handler | `clinical_media/scanner.py:run_next_stored_patient_media_scan` |
| Trigger | Upload creates a `background_jobs` row with `job_type='patient_media_scan'` |
| What it does | Reads stored file, validates SHA-256 + size match, checks magic bytes against MIME type |
| Sets | `patient_media.scan_status` to `clean`/`quarantined`/`scan_failed` |
| Idempotent | Yes — overwrites scan_status, inserts scan_event row |
| Uses claim_next_job | Yes — `SKIP LOCKED` safe |
| Runs in embedded worker | **Yes** |
| Delay tolerance | Minutes — media not served until scanned |
| Frequency needed | Continuous (within seconds of upload) |

### 2. `website_media_scan`

| Field | Value |
|-------|-------|
| Handler | `websites/scanner.py:run_next_stored_website_media_scan` |
| Trigger | Website media upload |
| What it does | Same validation as patient_media_scan |
| Sets | `website_media.scan_status` |
| Idempotent | Yes |
| Uses claim_next_job | Yes |
| Runs in embedded worker | **Yes** |
| Delay tolerance | Minutes |
| Frequency needed | On-demand |

### 3. `document_scan`

| Field | Value |
|-------|-------|
| Handler | `files/jobs.py:run_next_stored_document_scan` |
| Trigger | Patient document upload |
| What it does | Reads stored document, calls `scan_document_bytes` |
| Sets | `patient_documents.scan_status` |
| Idempotent | Yes |
| Uses claim_next_job | Yes |
| Runs in embedded worker | **Yes** |
| Delay tolerance | Minutes |
| Frequency needed | On-demand |

### 4. `document_metadata_encrypt`

| Field | Value |
|-------|-------|
| Handler | `files/jobs.py:run_next_document_metadata_encryption` |
| Trigger | Migration queues one job per existing document with plaintext filename |
| What it does | Encrypts `original_filename` into `original_filename_ciphertext`, replaces plaintext with generic name |
| Security | Removes PHI (patient document filenames) from plaintext column |
| Idempotent | Yes — checks `original_filename_ciphertext` before encrypting, uses `FOR UPDATE` row lock |
| Uses claim_next_job | Yes |
| Runs in embedded worker | **NO — MISSING** |
| Delay tolerance | Low — plaintext PHI exposure until encryption runs |
| Frequency needed | Once per document (migration backfill) |

### 5. `export`

| Field | Value |
|-------|-------|
| Handler | `governance/jobs.py:run_next_export_job` |
| Trigger | User requests a data export (patient access request, audit log) |
| What it does | Builds JSON from patient/audit data, stores in private storage, creates download token |
| Idempotent | Yes — `claim_next_job` prevents double-claiming |
| Uses claim_next_job | Yes |
| Runs in embedded worker | **NO — MISSING** |
| Delay tolerance | Low — user is waiting for their export |
| Frequency needed | On-demand |

### 6. `retention_cleanup`

| Field | Value |
|-------|-------|
| Handler | `governance/jobs.py:run_expired_artifact_cleanup` |
| Trigger | Called by worker for each clinic |
| What it does | Deletes expired export files from storage, removes download tokens, cleans expired preview tokens |
| Safety | Uses `FOR UPDATE` on expired rows, tenant-scoped via `set_tenant_context` |
| Idempotent | Yes — only processes `status='completed'` with `expires_at <= now()` |
| Runs in embedded worker | **NO — MISSING** |
| Delay tolerance | Hours — governance artifacts linger slightly |
| Frequency needed | Periodic (hours) |

### 7. `follow_up_overdue_notification`

| Field | Value |
|-------|-------|
| Handler | `operations/jobs.py:run_overdue_follow_up_job` |
| Trigger | Called by worker for each clinic every poll cycle |
| What it does | Finds overdue follow-up tasks, creates in-app notifications, delivers push |
| Deduplication | `ON CONFLICT (clinic_id, job_key) DO NOTHING` on job creation; `ON CONFLICT (clinic_id, user_id, source_job_key) DO NOTHING` on notifications |
| Idempotent | **Yes — double execution is safe** |
| Runs in embedded worker | **Yes** |
| Delay tolerance | Minutes to hours |
| Frequency needed | Periodic (minutes) |

### 8. `session_cleanup`

| Field | Value |
|-------|-------|
| Handler | `identity/jobs.py:run_session_cleanup` |
| Trigger | Called by worker for each clinic |
| What it does | Deletes expired sessions (revoked >24h, idle-expired >24h, absolute-expired >24h), stale rate-limit buckets, expired reset tokens |
| Auth impact | **None** — expired sessions are rejected by auth checks before cleanup runs (via `idle_expires_at`/`absolute_expires_at` column checks in session validation) |
| Idempotent | Yes — DELETE with WHERE conditions |
| Runs in embedded worker | **NO — MISSING** |
| Delay tolerance | Hours to days — DB hygiene only |
| Frequency needed | Periodic (hours) |

---

## Summary of Missing Jobs

| Job Type | Runs in Embedded Worker | Impact of Not Running |
|----------|------------------------|----------------------|
| `document_metadata_encrypt` | NO | Plaintext PHI lingers |
| `export` | NO | Users never receive exports |
| `retention_cleanup` | NO | Expired artifacts accumulate |
| `session_cleanup` | NO | Stale DB rows accumulate |

**Root cause**: `scripts/scan_worker.py` was written for scanning only. Its `SCAN_TYPES` tuple and the `follow_up_overdue_notification` sweep are hardcoded. The remaining 4 job types in `app/worker.py:HANDLERS` are only callable via the CLI worker (`python -m app.worker --clinic-id X --job-type Y`), which is never launched on Render.

---

## Duplicate Worker Thread Analysis

With `WEB_CONCURRENCY=2` and no `--preload`:

1. Gunicorn master forks 2 worker processes.
2. Each worker process loads `app.main:app`.
3. Each triggers `_start_embedded_worker()`.
4. Result: **2 polling loops**, each with its own DB connections.

**Queue-based jobs** (`patient_media_scan`, `website_media_scan`, `document_scan`): Safe — `SKIP LOCKED` prevents double-claiming.

**Non-queue sweep** (`follow_up_overdue_notification`): Safe — uses `ON CONFLICT DO NOTHING`.

**Resource waste**: 2 loops × `active_clinics()` query every 5s + 2 × (3 scan-type queries + 1 follow-up query) per clinic per cycle. At minimum: 2 extra DB connections held permanently.

**Recommended fix**: Set `WEB_CONCURRENCY=1` on Render Free (512MB RAM fits 1 worker comfortably), which also solves the duplicate thread issue. Add the 4 missing job types to `scan_worker.py`.
