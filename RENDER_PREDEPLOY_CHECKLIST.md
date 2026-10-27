# Pre-Deploy Checklist

## Readiness Decision: **BLOCKED**

All code/configuration work is complete. Deployment is blocked on Render billing verification and Neon secret entry.

---

## Code & Configuration

| # | Item | Status | Evidence |
|---|------|--------|---------|
| 1 | Docker image builds | **PASS** | `docker build -t healthcare-api-test .` → success |
| 2 | App imports correctly in container | **PASS** | `docker run ... python3 -c "from app.main import app"` → 57 routes |
| 3 | All 8 job types in worker | **PASS** | Import test: SCAN_TYPES(3) + QUEUE_TYPES(3) + follow_up + session_cleanup |
| 4 | Single worker thread (WEB_CONCURRENCY=1) | **PASS** | render.yaml updated |
| 5 | DB pool sized for single process | **PASS** | pool_size=3, max_overflow=5 → max 8 connections |
| 6 | Connect timeout handles Neon cold start | **PASS** | DATABASE_CONNECT_TIMEOUT=10 |
| 7 | Health check verifies DB + storage | **PASS** | main.py:254 — SELECT 1 + check_storage_readiness() |
| 8 | Migrations run conditionally | **PASS** | docker-entrypoint.sh checks RUN_MIGRATIONS_ON_START |
| 9 | Alembic uses correct DB URL | **PASS** | env.py:11 — uses DATABASE_MIGRATION_URL, falls back to DATABASE_URL |
| 10 | No render-managed database | **PASS** | No `databases:` section in render.yaml |
| 11 | No secrets in render.yaml values | **PASS** | All 8 secrets use `sync: false` |
| 12 | Job claiming uses SKIP LOCKED | **PASS** | operations/jobs.py:39 |
| 13 | Stale job recovery (5 min timeout) | **PASS** | operations/jobs.py:27,37 |
| 14 | Path traversal protection on storage | **PASS** | storage.py:89-97, 134-141 |
| 15 | Tests pass (excluding pre-existing failures) | **PASS** | 323 passed, 5 pre-existing failures, 41 skipped |

## External Requirements

| # | Item | Status | Action Needed |
|---|------|--------|--------------|
| 16 | Render billing verification | **BLOCKED** | Add credit card to Render account |
| 17 | DATABASE_URL set in Render | **BLOCKED** | Enter Neon pooled connection string |
| 18 | DATABASE_MIGRATION_URL set in Render | **BLOCKED** | Enter Neon direct connection string (migrator role) |
| 19 | SESSION_HMAC_KEY set in Render | **BLOCKED** | Enter unique staging secret |
| 20 | FIELD_ENCRYPTION_KEYS set in Render | **BLOCKED** | Enter encryption key |
| 21 | CSRF_ALLOWED_ORIGINS set in Render | **BLOCKED** | Enter Vercel frontend URL |
| 22 | CORS_ORIGINS set in Render | **BLOCKED** | Enter Vercel frontend URL |
| 23 | PUBLIC_APP_URL set in Render | **BLOCKED** | Enter Vercel frontend URL |
| 24 | COOKIE_DOMAIN set in Render | **BLOCKED** | Set to empty string |

## Post-Deploy Verification (after BLOCKED items resolved)

| # | Item | Status |
|---|------|--------|
| 25 | Render service starts | NOT RUN |
| 26 | /health/ready returns 200 | NOT RUN |
| 27 | Migrations complete successfully | NOT RUN |
| 28 | Worker thread starts (check logs) | NOT RUN |
| 29 | Login works from Vercel frontend | NOT RUN |
| 30 | Receptionist login without admin | NOT RUN |
| 31 | Doctor login without admin | NOT RUN |
| 32 | Login from different device, laptop off | NOT RUN |
| 33 | API responds after spin-down wake | NOT RUN |
| 34 | Worker resumes after spin-down wake | NOT RUN |

## Deployment Steps (once billing is resolved)

1. Add payment method in Render dashboard
2. Create web service from repo (or use render.yaml Blueprint)
3. Set Root Directory to `apps/api` if creating manually (Blueprint handles this via dockerContext)
4. Enter 8 secret environment variables (#17-24 above)
5. Deploy
6. Watch build logs for `docker build` success
7. Watch deploy logs for `[entrypoint] applying migrations` + `connection_pool_warmed` + `embedded_scan_worker_started`
8. Hit `/health/ready` — expect `{"status": "ready"}`
9. Update Vercel `API_URL` to Render service URL
10. Redeploy Vercel frontend
11. Test login from browser
12. Test login from different device with laptop off
