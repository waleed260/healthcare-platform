# Render Deployment Audit

## Service Configuration

**Source**: `render.yaml`

| Field | Value | Verified Against |
|-------|-------|-----------------|
| type | `web` | render.yaml:6 |
| name | `healthcare-api` | render.yaml:7 |
| runtime | `docker` | render.yaml:8 |
| repo | `https://github.com/waleed260/healthcare-platform` | render.yaml:9 |
| branch | `main` | render.yaml:10 |
| dockerfilePath | `./apps/api/Dockerfile` | render.yaml:11 — file exists |
| dockerContext | `./apps/api` | render.yaml:12 — directory exists |
| plan | `free` | render.yaml:13 |
| region | `frankfurt` | render.yaml:14 |
| healthCheckPath | `/health/ready` | render.yaml:15 — endpoint exists at `main.py:254` |

## Dockerfile Verification

**Source**: `apps/api/Dockerfile`

- Multi-stage: `python:3.12-slim` builder + runtime. **Correct.**
- Installs deps with `pip install --prefix=/install`. **Correct — copies to `/usr/local` in runtime stage.**
- `COPY . .` copies entire `apps/api/` into `/app`. **Correct — includes `scripts/`, `app/`, `migrations/`, `alembic.ini`, `requirements.txt`.**
- Creates non-root `appuser`, creates `/tmp/healthcare-private` and `/tmp/healthcare-public`. **Correct.**
- `WORKDIR /app` and `PYTHONPATH=/app`. **Correct — `from app.xxx` and `from scripts.xxx` imports will resolve.**
- `ENTRYPOINT ["scripts/docker-entrypoint.sh"]`. **Correct — file exists, is `chmod +x`.**
- `CMD` runs gunicorn with `--bind 0.0.0.0:${PORT:-8000}`. **Correct — reads Render's `PORT` env var.**
- `--workers ${WEB_CONCURRENCY:-4}` — defaults to 4 if env var missing. **render.yaml sets it to 2.**
- `--forwarded-allow-ips` reads from env var. **Correct.**

## Entrypoint Verification

**Source**: `apps/api/scripts/docker-entrypoint.sh`

```sh
if [ "${RUN_MIGRATIONS_ON_START:-false}" = "true" ]; then
  alembic upgrade head
fi
exec "$@"
```

- Runs migrations only when `RUN_MIGRATIONS_ON_START=true`. **Correct — set in render.yaml.**
- Uses `exec "$@"` to replace shell with gunicorn. **Correct — signals propagate to gunicorn for clean shutdown.**
- Alembic uses `DATABASE_MIGRATION_URL` (via `migrations/env.py:11`). Falls back to `DATABASE_URL` if migration URL is empty.

## Health Check Verification

**Source**: `apps/api/app/main.py:254-268`

```python
@app.get("/health/ready")
def health_ready():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    storage_ready = check_storage_readiness()
```

**Checks performed:**
1. PostgreSQL connectivity — executes `SELECT 1` on the actual engine. **Real check, not a stub.**
2. Storage readiness — for `STORAGE_BACKEND=local`, verifies dirs exist and are readable/writable. For `supabase`, hits the Supabase API.

**Failure behavior:**
- DB unreachable → `503 Service Unavailable`. **Correct.**
- Storage unready → `503 Service Unavailable`. **Correct.**
- Exception during check → `503`. **Correct.**

**No false-positive risk identified.** Render will not mark the service healthy if the DB or storage is down.

## CONFIRMED DEFECTS

### DEFECT 1: Duplicate Worker Threads (HIGH)

**Evidence:** `main.py:228-239` — `_start_embedded_worker` runs as a `startup` event. Gunicorn forks `WEB_CONCURRENCY=2` worker processes. No `--preload` flag exists (verified: no `gunicorn.conf.py`, no preload in CMD). Each forked process independently loads the FastAPI app and executes all startup events.

**Result:** Two identical `scan_worker.main()` polling loops start — one per gunicorn worker.

**Impact:** Queue-based jobs (`patient_media_scan`, `website_media_scan`, `document_scan`) use `FOR UPDATE SKIP LOCKED` (`operations/jobs.py:29-39`) so they won't double-process. But the `follow_up_overdue_notification` sweep runs in both — uses `ON CONFLICT DO NOTHING` so it's idempotent. Double the DB polling load and connection usage, but no data corruption.

**Fix:** Guard `_start_embedded_worker` with `os.environ.get("GUNICORN_WORKER_ID")` or a file lock so only one process starts the thread. OR set `WEB_CONCURRENCY=1` for the free tier. See implementation plan.

### DEFECT 2: Only 4 of 8 Job Types Run (HIGH)

**Evidence:** `scripts/scan_worker.py:21-22` — `SCAN_TYPES = ("patient_media_scan", "website_media_scan", "document_scan")`. The main loop (lines 40-53) processes these three types plus `follow_up_overdue_notification`.

**Missing from embedded worker:**
- `session_cleanup` — expired sessions accumulate in DB
- `document_metadata_encrypt` — unencrypted filenames remain in plaintext
- `export` — export jobs stay in `queued` state forever
- `retention_cleanup` — expired artifacts (export files, preview tokens) are never cleaned up

**Impact:**
- `session_cleanup`: LOW — auth checks reject expired sessions via `idle_expires_at`/`absolute_expires_at` column checks. Cleanup is only for DB hygiene.
- `document_metadata_encrypt`: MEDIUM — legacy plaintext filenames remain unencrypted until this runs. Security degradation.
- `export`: HIGH — users requesting data exports will never receive them.
- `retention_cleanup`: MEDIUM — expired export files and preview tokens linger.

**Fix:** Add the missing 4 job types to `scan_worker.py`'s main loop. See implementation plan.

### DEFECT 3: Storage is Ephemeral on Render Free (MEDIUM)

**Evidence:** `render.yaml:51` sets `STORAGE_BACKEND=local`. Files write to `/tmp/healthcare-private` and `/tmp/healthcare-public`. Render free tier uses ephemeral filesystem — files survive within a running container but are lost on deploy, restart, or spin-down wake.

**Impact:** File uploads (patient documents, clinical media, website images) will succeed but may be lost. Export files stored via `put_private_object` will be unreadable after restart.

**Mitigation:** For staging with no real patient data, this is tolerable. For any real use, must switch to `STORAGE_BACKEND=supabase`.

### DEFECT 4: Render Free Spin-Down Kills Worker (MEDIUM)

**Evidence:** Render free tier spins down after 15 minutes of no HTTP requests. The process is terminated (SIGTERM). The daemon worker thread is killed immediately (Python daemon threads don't get cleanup). Any in-progress job will have `status='running'` and `locked_at` set.

**Recovery:** `claim_next_job` reclaims stale jobs where `status = 'running' AND locked_at < now - 5 minutes` (`operations/jobs.py:37`). Jobs recover on next wake. **No data corruption, but jobs can be delayed by hours if no HTTP traffic arrives.**

**Impact:** Background processing is paused during spin-down. For staging this is acceptable.
