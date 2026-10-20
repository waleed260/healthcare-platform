# Admin-Independent Access Audit

**Date**: 2026-10-20
**Scope**: Full authentication flow — from frontend login form to database session creation
**Objective**: Identify why non-admin users cannot log in until the admin logs in first each day

---

## Executive Summary

A structural flaw in the login route handler caused **any non-authentication error** (database connection timeout, audit table RLS violation, connection pool exhaustion) to surface as an unhandled HTTP 500, which the frontend displayed as "Something went wrong. Try again shortly." The admin was never technically required — they simply absorbed the transient cold-start failures by being the first to retry, after which the connection pool recovered and other users could log in.

---

## Components Audited

| Component | File | RLS? | Risk |
|---|---|---|---|
| Login route handler | `app/modules/identity/routes.py:login()` | N/A | **CRITICAL** — only catches `AuthenticationError` |
| Authentication service | `app/modules/identity/service.py:authenticate()` | No | Low — queries `users` (no RLS) |
| Session creation | `app/modules/identity/service.py:_start_session()` | Partial | Medium — queries `user_roles` (RLS + FORCE) |
| Audit logging | `app/modules/audit/service.py:record_event()` | Yes | **HIGH** — `audit_events` has FORCE RLS |
| Tenant context | `app/db/tenant.py:set_tenant_context()` | N/A | Low — sets `app.clinic_id` config |
| Connection pool | `app/db/session.py` | N/A | Medium — 2s connect timeout, 300s recycle |
| Pool warmup | `app/main.py:_warm_pool()` | N/A | Low — runs once at startup, no retry |
| Frontend login page | `apps/web/app/login/page.tsx` | N/A | Low — displays generic error for non-401 |
| API client | `apps/web/app/(authenticated)/_lib/client.ts` | N/A | Low — redirects on 401 only |

## Tables and RLS Status

### Auth tables (NO RLS — correct)
- `users` — queried during `authenticate()`
- `sessions` — INSERT during `_start_session()`
- `mfa_methods` — queried during `_start_session()`
- `recovery_codes` — used during MFA recovery
- `auth_rate_limit_buckets` — rate limiting
- `roles` — role definitions
- `permissions` — permission definitions
- `role_permissions` — role-permission mapping

### Tables with RLS + FORCE (tenant-scoped)
- `user_roles` — queried during `_start_session()` for MFA policy (context set first)
- `audit_events` — INSERT during `record_event()` in login handler (context set first)
- `branches`, `user_branch_scopes` — not used during login

---

## Root Cause Analysis

### Issue 1: Login handler catches only `AuthenticationError`

```python
# BEFORE (vulnerable)
@router.post("/login")
def login(...):
    try:
        result = authenticate(...)
        record_event(...)       # <-- if THIS throws, entire login fails
        db.commit()
        return {...}
    except AuthenticationError:  # <-- ONLY this type caught
        db.rollback()
        raise 401
    # Any other exception → unhandled → HTTP 500
```

**Impact**: Database connection errors, RLS violations in audit logging, transaction timeouts, and any other non-`AuthenticationError` exception propagated as an unhandled 500. The frontend cannot distinguish this from a server crash and shows a generic error.

### Issue 2: Audit logging in the critical login path

`record_event()` inserts into `audit_events`, which has `FORCE ROW LEVEL SECURITY`. This insert runs inside the same transaction as the session creation. If the audit INSERT fails for any reason (stale connection, RLS policy mismatch, lock timeout), the `db.commit()` is never reached and the session is lost.

**Impact**: Audit logging failure = login failure. Audit should be best-effort for the login path — a failed audit entry should never prevent a user from authenticating.

### Issue 3: Aggressive connection timeout

`database_connect_timeout` was set to **2 seconds**. For remote/serverless databases that need cold-start time (Neon, Supabase, scale-to-zero RDS), 2 seconds is insufficient. The first connection attempt after overnight inactivity would timeout, and `pool_pre_ping=True` would discard the stale connection but the replacement attempt could also fail within 2s.

### Issue 4: Non-resilient pool warmup

`_warm_pool()` ran once at application startup with no retry logic. If the database wasn't ready at that exact moment, all pool_size slots remained cold, and every subsequent first request needed to establish a new connection — hitting the 2s timeout.

---

## Why It Appeared Admin-Dependent

The daily pattern was:

1. **Overnight**: All pool connections expire (`pool_recycle=300`) or go stale
2. **Morning**: First user (usually admin, since they arrive first) tries to log in
3. **First attempt**: `pool_pre_ping` detects stale connection → discards it → attempts new connection → 2s timeout may fail → `authenticate()` throws a DB error → unhandled 500
4. **Retries**: Admin retries a few times, each attempt forces the pool to establish new connections
5. **Pool recovered**: After 2-3 retries, enough live connections exist
6. **Other users**: Now the pool has live connections, so their logins succeed immediately

The admin was never a prerequisite. They were simply the person who absorbed the cold-start failures by arriving first and retrying.

---

## Security Verification

| Control | Status | Evidence |
|---|---|---|
| RLS tenant isolation | **Intact** | `set_tenant_context()` called before any RLS-protected query |
| Session auth (opaque tokens) | **Intact** | No changes to `authenticate()` or `_start_session()` |
| CSRF double-submit | **Intact** | `_validate_origin()` still runs before any login logic |
| Rate limiting | **Intact** | `auth_rate_limit_buckets` checked before password verification |
| Password hashing | **Intact** | `verify_password()` unchanged |
| MFA flow | **Intact** | `mfa_methods` query unchanged |
| Audit immutability | **Intact** | `audit_events` immutable trigger unchanged; audit is now best-effort for login only |

---

## Recommendations Applied

1. **Best-effort audit in login path** — `record_event()` wrapped in try/except; failures logged, not propagated
2. **Broad exception handler** — Non-`AuthenticationError` exceptions return HTTP 503 with structured JSON
3. **Increased connect timeout** — Default raised from 2s to 5s
4. **Resilient pool warmup** — Retry with backoff (3 attempts)
5. **Consistent logout audit** — Same best-effort pattern applied to logout
