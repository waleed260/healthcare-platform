# Final Review

## Source Diff Review

### `apps/api/scripts/scan_worker.py`

**Added**: `QUEUE_TYPES` tuple with 3 job types. Drain loop matching existing `SCAN_TYPES` pattern. `session_cleanup` call matching existing `follow_up_overdue_notification` pattern.

- Uses the same `process_once()` function as existing code. **Correct.**
- Same `try/except` + logging pattern. **Correct.**
- Same `MAX_DRAIN` limit on queue types. **Correct.**
- `session_cleanup` called once per clinic per cycle (like `follow_up`), not drained. **Correct** — it's not a queue-based job, it's a sweep that processes a batch internally.
- No new imports needed — `process_once` already handles all types. **Correct.**

**No security regression. No behavior change for existing 4 job types.**

### `render.yaml`

**Changed**:
- `WEB_CONCURRENCY`: `2` → `1` — eliminates duplicate worker threads, fits 512MB RAM
- `DB_POOL_SIZE`: `5` → `3` — right-sized for single process
- `DB_MAX_OVERFLOW`: `10` → `5` — right-sized for single process
- **Added** `DATABASE_CONNECT_TIMEOUT=10` — handles Neon scale-to-zero cold starts
- Header comment updated

**No secret values changed. No service type changed. No plan changed.**

## Configuration Verification

| Check | Status |
|-------|--------|
| Dockerfile path correct | PASS — `./apps/api/Dockerfile` exists |
| Build context correct | PASS — `./apps/api` directory exists |
| Health check path exists | PASS — `main.py:254` defines `/health/ready` |
| Health check verifies DB | PASS — executes `SELECT 1` |
| Health check verifies storage | PASS — calls `check_storage_readiness()` |
| Entrypoint runs migrations conditionally | PASS — checks `RUN_MIGRATIONS_ON_START` |
| Entrypoint uses exec for signal handling | PASS — `exec "$@"` |
| Port reads from env var | PASS — `${PORT:-8000}` in CMD |
| Worker thread starts only once (WEB_CONCURRENCY=1) | PASS |
| All 8 job types processed | PASS — verified via import test |
| Job claiming uses SKIP LOCKED | PASS — `operations/jobs.py:39` |
| Stale job recovery exists | PASS — `locked_at < stale_before` clause |
| Failed jobs retry with backoff | PASS — exponential backoff, max 5 attempts |
| RLS preserved through migrations | PASS — migrations are DDL-only |
| Alembic uses NullPool | PASS — `migrations/env.py:26` |
| No localhost fallback in Neon config | PASS — DATABASE_URL `sync: false`, default fails safely |
| Storage path traversal protected | PASS — `_safe_path()` rejects `..` and absolute paths |
| Session auth independent of admin | PASS — opaque tokens, DB-backed, no local dependency |
| CSRF validation correct | PASS — checks Origin header against allowed origins |
| No secrets in render.yaml values | PASS — all secrets use `sync: false` |

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Render billing blocks deploy | HIGH | User must add credit card |
| Free tier spin-down pauses worker | MEDIUM | Jobs resume on wake; acceptable for staging |
| Ephemeral storage loses uploads | MEDIUM | No real patient data in staging; switch to Supabase for prod |
| Single gunicorn worker limits throughput | LOW | Staging only; async uvicorn still handles concurrency |
| Neon cold start on first request | LOW | `DATABASE_CONNECT_TIMEOUT=10` and `pool_pre_ping=True` |
