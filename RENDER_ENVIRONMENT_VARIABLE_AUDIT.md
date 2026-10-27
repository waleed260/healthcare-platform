# Environment Variable Audit

Complete inventory rebuilt from `app/core/config.py` and `render.yaml`.

## Required Variables (must be set for staging)

| # | Variable | Secret | Default | render.yaml | Must Set in Dashboard |
|---|----------|--------|---------|-------------|----------------------|
| 1 | `DATABASE_URL` | YES | localhost (will fail) | `sync: false` | **YES** |
| 2 | `DATABASE_MIGRATION_URL` | YES | empty (falls back to DATABASE_URL) | `sync: false` | **YES** (use migrator role) |
| 3 | `SESSION_HMAC_KEY` | YES | dev placeholder (rejected in prod) | `sync: false` | **YES** |
| 4 | `FIELD_ENCRYPTION_KEYS` | YES | empty | `sync: false` | **YES** |
| 5 | `CSRF_ALLOWED_ORIGINS` | NO* | `http://localhost:3000` | `sync: false` | **YES** (Vercel URL) |
| 6 | `CORS_ORIGINS` | NO* | empty (falls back to CSRF) | `sync: false` | **YES** (Vercel URL) |
| 7 | `PUBLIC_APP_URL` | NO* | `http://localhost:3000` | `sync: false` | **YES** (Vercel URL) |
| 8 | `COOKIE_DOMAIN` | NO* | empty | `sync: false` | **YES** (empty string) |

*Marked `sync: false` in render.yaml because they contain the frontend URL which varies per deployment, not because they're secrets.

## Pre-configured Variables (set in render.yaml, no action needed)

| # | Variable | Value | Rationale |
|---|----------|-------|-----------|
| 9 | `APP_ENV` | `staging` | Not production — skips strict validations |
| 10 | `PORT` | `10000` | Render's required port |
| 11 | `WEB_CONCURRENCY` | `2` | **Should be 1 — see defect** |
| 12 | `DB_POOL_SIZE` | `5` | **Should be 3 for single worker** |
| 13 | `DB_MAX_OVERFLOW` | `10` | **Should be 5 for single worker** |
| 14 | `FORWARDED_ALLOW_IPS` | `*` | Trust Render's proxy |
| 15 | `ALLOW_WILDCARD_FORWARDED_IPS` | `true` | Required for wildcard IPs in non-prod |
| 16 | `RUN_MIGRATIONS_ON_START` | `true` | Entrypoint runs alembic |
| 17 | `RUN_WORKER_IN_PROCESS` | `true` | Background jobs run in-process |
| 18 | `STORAGE_BACKEND` | `local` | Ephemeral — acceptable for staging |

## Optional Variables (not in render.yaml, have safe defaults)

| # | Variable | Default | Purpose |
|---|----------|---------|---------|
| 19 | `SENTRY_DSN` | empty | Error tracking — disabled if empty |
| 20 | `GOOGLE_CLIENT_ID` | empty | Google OAuth — disabled if empty |
| 21 | `GOOGLE_CLIENT_SECRET` | empty | Google OAuth |
| 22 | `GOOGLE_REDIRECT_URI` | empty (auto-derived from PUBLIC_APP_URL) | Google OAuth callback |
| 23 | `DB_POOL_TIMEOUT` | `30` | Not in render.yaml — default fine |
| 24 | `DB_POOL_RECYCLE` | `300` | Not in render.yaml — default fine |
| 25 | `DATABASE_CONNECT_TIMEOUT` | `5` | May need increase for Neon cold start |
| 26 | `VAPID_SUBJECT` | empty | Push notifications — disabled if empty |
| 27 | `VAPID_PRIVATE_KEY` | empty | Push notifications |
| 28 | `VAPID_PUBLIC_KEY` | empty | Push notifications |
| 29 | `PUBLIC_WEBSITE_DOMAIN` | empty | Clinic public website domain |
| 30 | `SUPABASE_URL` | empty | Only needed if `STORAGE_BACKEND=supabase` |
| 31 | `SUPABASE_SERVICE_ROLE_KEY` | empty | Only needed if `STORAGE_BACKEND=supabase` |
| 32 | `SUPABASE_PRIVATE_BUCKET` | `private-healthcare` | Only needed if `STORAGE_BACKEND=supabase` |
| 33 | `SUPABASE_PUBLIC_BUCKET` | `public-healthcare` | Only needed if `STORAGE_BACKEND=supabase` |
| 34 | `WORKER_POLL_SECONDS` | `5` | Worker poll interval (read by scan_worker.py) |

## Validation Behavior

**`APP_ENV=staging`**: The `validate_production_secrets` model validator (config.py:140-168) **only runs when `app_env == "production"`**. In staging, missing or placeholder secrets do NOT cause startup failure. The app will start even with the default dev SESSION_HMAC_KEY.

**However**, the default SESSION_HMAC_KEY (`"local-development-session-hmac-key-change-me"`) is a known value. If used in staging, anyone who reads the source code can forge session tokens. **Must set a unique SESSION_HMAC_KEY even for staging.**

**`FORWARDED_ALLOW_IPS=*`**: The `validate_forwarded_ip_trust` validator (config.py:127-136) rejects wildcard in `production` unless `ALLOW_WILDCARD_FORWARDED_IPS=true`. In `staging`, the wildcard is accepted regardless. But render.yaml sets both `FORWARDED_ALLOW_IPS=*` and `ALLOW_WILDCARD_FORWARDED_IPS=true`, covering all environments.

## Proxy Security Analysis

`FORWARDED_ALLOW_IPS=*` means gunicorn trusts `X-Forwarded-For` from any source. On Render, all traffic comes through Render's proxy infrastructure, which sets `X-Forwarded-For` correctly. Direct client access is not possible — Render's ingress layer is the only path.

**Impact**: The rate limiter (`app/core/rate_limit.py`) uses session cookie tokens, not IP addresses. The security middleware reads `request.cookies.get(settings.session_cookie_name)` for rate limit keys. **IP spoofing via X-Forwarded-For does NOT affect rate limiting.**

Audit logging records the request_id, not the client IP. **No security impact from wildcard forwarded IPs on Render.**

## Env Var Count

- **render.yaml declares 22 entries** (18 `envVars` + 4 Google OAuth entries)
- **8 must be set manually** in the Render dashboard (secrets + frontend URLs)
- **14 are pre-configured** with values in render.yaml
- **16 optional variables** have safe defaults and need no action

**Previous summary reported 18 variables — actual count is 22 declared in render.yaml.** The discrepancy was because Google OAuth variables (lines 55-60) were not counted.
