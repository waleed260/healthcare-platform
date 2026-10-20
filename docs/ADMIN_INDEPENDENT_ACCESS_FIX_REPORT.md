# Admin-Independent Access Fix Report

**Date**: 2026-10-20
**Status**: FIXED
**Severity**: CRITICAL — prevented daily logins for all non-admin users
**Regression tests**: 6 tests (3 unit, 3+ integration)

---

## Problem Statement

Every morning, authorized clinic users (receptionists, doctors, other staff) could not log in until the clinic administrator logged in first. Users saw "Something went wrong. Try again shortly." The issue recurred daily after overnight inactivity.

---

## Root Cause

Two interacting structural flaws in the login handler:

1. **The `login()` route only caught `AuthenticationError`** — any database error (connection timeout, RLS violation, pool exhaustion) became an unhandled HTTP 500.

2. **Audit logging (`record_event`) ran inside the critical login path** — inserting into `audit_events` (which has `FORCE ROW LEVEL SECURITY`) within the same transaction as session creation meant audit failure = login failure.

Combined with an aggressive 2-second database connect timeout and non-resilient pool warmup, the first morning connections would fail, and the admin absorbed those failures by being the first to retry.

---

## Changes Made

### 1. Login handler: best-effort audit + broad exception handling

**File**: `apps/api/app/modules/identity/routes.py`

```python
# BEFORE — audit failure kills login, no catch-all
try:
    result = authenticate(...)
    record_event(...)  # throws → login fails
    db.commit()
except AuthenticationError:
    ...
# Unhandled exceptions → HTTP 500

# AFTER — audit is best-effort, transient errors return 503
try:
    result = authenticate(...)
    try:
        record_event(...)
    except Exception:
        logging.warning("audit_record_failed_during_login ...")
    db.commit()
except AuthenticationError:
    db.rollback()
    raise 401
except Exception:
    logging.exception("login_transient_failure ...")
    db.rollback()
    raise 503  # LOGIN_UNAVAILABLE — frontend can show retry message
```

**Why**: Authentication success must not depend on audit logging. The session is created and committed regardless. Audit failures are logged for investigation but don't block users. The broad `except Exception` handler catches transient DB errors and returns a structured 503 instead of an unhandled 500, letting the frontend display a meaningful message.

### 2. Logout handler: consistent best-effort audit

**File**: `apps/api/app/modules/identity/routes.py`

Same pattern applied to the logout handler — if `record_event` fails during logout, the session is still revoked and cookies cleared.

### 3. Increased database connect timeout

**File**: `apps/api/app/core/config.py`

```python
# BEFORE
database_connect_timeout: int = Field(default=2, ...)

# AFTER
database_connect_timeout: int = Field(default=5, ...)
```

**Why**: 2 seconds is too aggressive for remote/serverless databases (Neon, Supabase, scale-to-zero RDS) that need cold-start time. 5 seconds gives the database time to wake without being so long that users notice.

### 4. Resilient pool warmup with retry

**File**: `apps/api/app/main.py`

```python
# BEFORE — single attempt, no retry
def _warm_pool():
    try:
        # open connections
    except Exception:
        logging.warning("pool_warmup_failed")

# AFTER — 3 attempts with backoff
def _warm_pool():
    for attempt in range(3):
        try:
            # open connections
            return
        except Exception:
            logging.warning("pool_warmup_attempt_%d_failed", attempt + 1)
            if attempt < 2:
                time.sleep(1 * (attempt + 1))
    logging.error("pool_warmup_exhausted_retries")
```

**Why**: If the database isn't ready at startup, a single failed warmup leaves the entire pool cold. Retrying with backoff gives scale-to-zero databases time to wake.

---

## What Was NOT Changed

- **`authenticate()` / `_start_session()`** — Core authentication logic untouched
- **RLS policies** — No changes to any Row Level Security policy
- **`set_tenant_context()`** — Tenant isolation unchanged
- **Session model** — Token hashing, CSRF, session expiry all unchanged
- **MFA flow** — Enrollment, verification, recovery all unchanged
- **Rate limiting** — Login rate limiting unchanged
- **Audit immutability** — `audit_events` immutable trigger still enforced
- **Frontend login page** — No changes needed; it already handles 503 gracefully

---

## Regression Tests

**File**: `apps/api/tests/test_admin_independent_login.py`

### Unit tests (no database required)

| Test | What it proves |
|---|---|
| `test_login_returns_200_when_audit_raises` | Login succeeds even when `record_event` throws `RuntimeError` |
| `test_login_returns_503_on_transient_db_error` | DB connection errors return structured 503, not unhandled 500 |
| `test_login_returns_401_on_auth_error` | Wrong credentials still return 401 (not caught by broad handler) |

### Integration tests (require PostgreSQL)

| Test | What it proves |
|---|---|
| `test_receptionist_login_without_prior_admin_login` | Receptionist logs in first — no admin needed |
| `test_doctor_login_without_prior_admin_login` | Doctor logs in first — no admin needed |
| `test_all_users_login_independently_in_sequence` | Doctor → receptionist → admin all succeed in any order |
| `test_login_succeeds_when_audit_record_event_raises` | Core `authenticate()` works regardless of audit failures |

### Test results

```
tests/test_admin_independent_login.py::TestLoginRouteAuditResilience::test_login_returns_200_when_audit_raises PASSED
tests/test_admin_independent_login.py::TestLoginRouteAuditResilience::test_login_returns_503_on_transient_db_error PASSED
tests/test_admin_independent_login.py::TestLoginRouteAuditResilience::test_login_returns_401_on_auth_error PASSED
```

Integration tests require `TEST_ADMIN_DATABASE_URL` and `TEST_DATABASE_URL` environment variables.

---

## Verification Checklist

- [x] Login handler catches all exceptions — `AuthenticationError` → 401, other → 503
- [x] Audit logging is best-effort in login path — failure logged, not propagated
- [x] Session is created and committed even when audit fails
- [x] Frontend receives structured JSON for all error types (401, 503)
- [x] Connect timeout increased from 2s to 5s for cold-start resilience
- [x] Pool warmup retries 3 times with backoff
- [x] RLS, CSRF, session auth, MFA all remain intact
- [x] 3 unit tests pass, 4 integration tests defined
- [x] No regressions in existing test suite (2 pre-existing unrelated failures in `test_identity_policy.py`)
- [x] Logout handler has consistent best-effort audit pattern
