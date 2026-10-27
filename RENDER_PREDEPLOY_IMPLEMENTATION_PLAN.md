# Render Pre-Deploy Implementation Plan

## Confirmed Defects and Fixes

### FIX 1: Add Missing Job Types to Embedded Worker

**Defect**: `scripts/scan_worker.py` only processes 4 of 8 job types. Missing: `document_metadata_encrypt`, `export`, `retention_cleanup`, `session_cleanup`.

**Evidence**: `scan_worker.py:21` — `SCAN_TYPES` tuple only contains scan types. The main loop (lines 40-53) only processes these + `follow_up_overdue_notification`.

**Fix**: Add `QUEUE_TYPES = ("document_metadata_encrypt", "export", "retention_cleanup")` and process them in the main loop. Add explicit `session_cleanup` call alongside `follow_up_overdue_notification`.

**Risk**: None — all added jobs use `claim_next_job` with `FOR UPDATE SKIP LOCKED` (or are idempotent DELETE operations). Adding them cannot break existing behavior.

**Status**: IMPLEMENTED. Verified: imports pass, all 8 job types accessible, Docker build succeeds.

### FIX 2: Reduce WEB_CONCURRENCY to 1

**Defect**: `WEB_CONCURRENCY=2` causes duplicate worker threads (each gunicorn worker process starts its own `_start_embedded_worker`).

**Evidence**: No `--preload` flag, no gunicorn config file. Each forked worker loads app independently.

**Fix**: Set `WEB_CONCURRENCY=1` in `render.yaml`. Single process = single worker thread. Also fits 512MB RAM better.

**Risk**: Reduced request throughput — single gunicorn worker handles all HTTP requests. Acceptable for staging. Uvicorn's async event loop still handles concurrent connections.

**Status**: IMPLEMENTED.

### FIX 3: Reduce DB Pool Size

**Defect**: `DB_POOL_SIZE=5` and `DB_MAX_OVERFLOW=10` = max 15 connections per process. Oversized for a single-worker staging deployment with Neon's pooler.

**Fix**: Set `DB_POOL_SIZE=3` and `DB_MAX_OVERFLOW=5` = max 8 connections. Plenty for staging.

**Status**: IMPLEMENTED.

### FIX 4: Add DATABASE_CONNECT_TIMEOUT

**Defect**: Default `database_connect_timeout=5` may be too short for Neon's scale-to-zero cold start (can take 3-7 seconds).

**Fix**: Set `DATABASE_CONNECT_TIMEOUT=10` in render.yaml.

**Status**: IMPLEMENTED.

## Items NOT Fixed (Require External Action)

### BLOCKED: Render Billing Verification

The Render account requires credit card verification to deploy even free-plan services. **No code fix possible.**

**Action needed**: Add a payment method in the Render dashboard.

### BLOCKED: Neon Connection Strings

`DATABASE_URL` and `DATABASE_MIGRATION_URL` are placeholders. Real Neon connection strings must be entered in the Render dashboard.

**Action needed**: Copy pooled and direct connection strings from Neon dashboard.

### ACKNOWLEDGED: Ephemeral Storage

`STORAGE_BACKEND=local` means file uploads are lost on container restart/redeploy. Acceptable for staging. Switch to `supabase` for any real patient data.

### ACKNOWLEDGED: Render Free Spin-Down

Worker thread stops during spin-down. Jobs recover on wake (stale job reclaim after 5 minutes). Acceptable for staging.
