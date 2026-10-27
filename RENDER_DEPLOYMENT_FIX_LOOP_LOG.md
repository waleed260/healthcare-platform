# Fix Loop Log

## Iteration 1: Missing Job Types

**Defect**: `scan_worker.py` processes only 4/8 job types.

**Evidence**: `SCAN_TYPES = ("patient_media_scan", "website_media_scan", "document_scan")` at line 21. Main loop lines 40-53 only iterates SCAN_TYPES + follow_up.

**Root cause**: `scan_worker.py` was written as a "scan worker" — it was never updated when `document_metadata_encrypt`, `export`, `retention_cleanup`, and `session_cleanup` jobs were added to `app/worker.py:HANDLERS`.

**Change**: Added `QUEUE_TYPES = ("document_metadata_encrypt", "export", "retention_cleanup")` and drain loop for these types. Added explicit `session_cleanup` call per clinic.

**Tests**:
- `python3 -c "from scripts.scan_worker import QUEUE_TYPES; print(QUEUE_TYPES)"` → OK
- `python3 -c "from app.worker import HANDLERS; ..."` → all 8 types verified
- `docker build` → success
- `docker run ... python3 -c "from scripts.scan_worker import ..."` → imports OK in container
- `pytest` → 323 passed, 5 failed (all pre-existing), 41 skipped

**Result**: FIXED.

## Iteration 2: Duplicate Worker Threads

**Defect**: `WEB_CONCURRENCY=2` starts 2 gunicorn workers, each running `_start_embedded_worker`.

**Evidence**: No `--preload` flag in Dockerfile CMD. No `gunicorn.conf.py` exists. `grep -rn "preload_app\|--preload" apps/api/` returned empty.

**Root cause**: Gunicorn without `--preload` loads the app in each forked worker process. FastAPI's `on_event("startup")` fires in each.

**Change**: Set `WEB_CONCURRENCY=1` in `render.yaml`.

**Tests**:
- Docker build → success
- `pytest` → same results as iteration 1 (no regression)

**Result**: FIXED.

## Iteration 3: Oversized Pool and Connect Timeout

**Defect**: `DB_POOL_SIZE=5, DB_MAX_OVERFLOW=10` oversized for single-worker staging. `DATABASE_CONNECT_TIMEOUT=5` may be too short for Neon cold start.

**Evidence**: `config.py:17` defaults to 5s. Neon scale-to-zero documented at 3-7s wake time.

**Change**: Set `DB_POOL_SIZE=3`, `DB_MAX_OVERFLOW=5`, `DATABASE_CONNECT_TIMEOUT=10` in `render.yaml`.

**Tests**: Docker build → success. pytest → no regression.

**Result**: FIXED.

## Outstanding

| Item | Status | Reason |
|------|--------|--------|
| Render billing | BLOCKED | Credit card required |
| Neon connection strings | BLOCKED | Must enter manually in dashboard |
| Vercel API_URL update | BLOCKED | Do not change until Render API verified |
| Pre-existing test failures (5) | NOT_FIXED | Unrelated to deployment changes |
