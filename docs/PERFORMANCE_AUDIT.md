# Performance Audit Report

**Date**: 2026-10-20
**Target**: care/fully CRM API (FastAPI + PostgreSQL + RLS)
**Method**: In-container load testing (httpx async, 50 concurrent, 15s measurement after 2s warmup)

---

## 1. Architecture Overview

| Layer | Technology | Configuration |
|-------|-----------|---------------|
| Process manager | Gunicorn 22 | 4 UvicornWorker processes |
| ASGI framework | FastAPI | Middleware: GZip, CORS, security |
| Database | PostgreSQL 16 | max_connections=200 |
| Connection pool | SQLAlchemy (psycopg3) | pool_size=10, max_overflow=20, pool_pre_ping=True |
| Auth | Opaque session tokens | HMAC-SHA256 hashed, Argon2 passwords |
| Tenant isolation | Row-Level Security | set_config('app.clinic_id', ...) per transaction |
| Caching | cachetools TTLCache (in-process) | Session: 30s TTL, Permissions: 60s TTL |
| Rate limiting | In-memory token bucket | 200 GET/min, 60 write/min per user |

### Request Lifecycle

1. Gunicorn accepts TCP connection on one of 4 workers
2. `security_middleware` runs: rate limit check, request ID assignment
3. `CORSMiddleware`: origin validation, CORS headers
4. `GZipMiddleware`: response compression (>=500 bytes)
5. Route handler executes (session lookup, permission check, business logic)
6. Response: security headers, cache-control, structured logging

---

## 2. Endpoint Inventory

| Category | Endpoint | Method |
|----------|----------|--------|
| Health | `/health/live` | GET |
| Health | `/health/ready` | GET |
| Auth | `/api/v1/auth/me` | GET |
| Dashboard | `/api/v1/operations/dashboard-summary` | GET |
| Reporting | `/api/v1/operations/reporting-summary` | GET |
| CRUD | `/api/v1/services`, `/branches`, `/doctors` | GET |
| CRUD | `/api/v1/appointments` | GET |
| CRUD | `/api/v1/operations/queue` | GET |
| CRUD | `/api/v1/patients`, `/leads` | GET |
| Finance | `/api/v1/finance/cashier-summary` | GET |
| Finance | `/api/v1/finance/commission-rules` | GET |
| CRUD | `/api/v1/encounters` | GET |
| CRUD | `/api/v1/operations/follow-ups` | GET |
| CRUD | `/api/v1/inventory/products` | GET |
| Admin | `/api/v1/staff/users`, `/staff/roles` | GET |
| Auth | `/api/v1/auth/login` | POST |

---

## 3. Root Causes Identified (Pre-Optimization)

### 3.1 Session Lookup Overhead
Every authenticated request ran a 4-table JOIN query (`sessions JOIN users JOIN clinics LEFT JOIN support_access_sessions`). At 50 concurrent requests, this created 50 simultaneous DB round-trips before business logic.

**Fix**: In-process TTLCache (30s TTL, 2048 entries) keyed by `token_hash`. Cache hit calls lightweight `apply_rls_config()` (two `set_config` calls, no table access). Cache miss runs full query and stores result.

### 3.2 Permission Check Overhead
`has_permission()` ran a multi-table EXISTS query (`user_roles JOIN role_permissions` with correlated `user_branch_scopes` subqueries) on every request.

**Fix**: In-process TTLCache (60s TTL, 4096 entries) keyed by `(user_id, clinic_id, permission_code, branch_id)`.

### 3.3 Query Multiplication
Dashboard summary executed 3 sequential queries; reporting summary 8-10; cashier summary 3-4; provider revenue 3.

**Fix**: Consolidated into CTE-based single queries (dashboard: 1 CTE, reporting: 3 CTEs, cashier: 1 CTE, provider revenue: 1 CTE).

### 3.4 Connection Pool Exhaustion
Default pool: 5 connections + 10 overflow = 15 max. With 2 workers, that's 30 total — insufficient for burst traffic.

**Fix**: Increased to pool_size=10, max_overflow=20 per worker (120 max across 4 workers). PostgreSQL max_connections=200.

### 3.5 Insufficient Workers
Default: 2 uvicorn workers (single process). CPU-bound Argon2 hashing blocked the event loop.

**Fix**: 4 gunicorn workers with UvicornWorker class. Gunicorn provides process management, auto-restart, graceful shutdown.

### 3.6 Missing Database Indexes
No indexes on high-traffic query paths:
- `appointments (clinic_id, archived_at, status, starts_at)` — dashboard, reporting, list
- `appointments (clinic_id, branch_id, archived_at, starts_at)` — branch-filtered queries
- `payments (clinic_id, paid_at)` — cashier/provider revenue date filters
- `invoices (clinic_id, issued_at, status)` — cashier/reporting financial
- `payment_allocations (clinic_id, invoice_id)` — provider revenue, financial CTEs
- `invoice_lines (clinic_id, invoice_id, provider_id)` — provider revenue GROUP BY
- `queue_entries (clinic_id, status, priority DESC, checked_in_at, id)` — queue pagination

**Fix**: Alembic migration `0080_performance_indexes` adds all 7 indexes.

### 3.7 Pool Warmup Bug
`_warm_pool()` only opened 1 connection instead of `pool_size`, leaving 9 connections cold on first burst.

**Fix**: Now opens `pool_size` connections in parallel during startup.

---

## 4. Profiling Evidence (EXPLAIN ANALYZE)

### Dashboard Summary CTE (after indexes)
```
Execution Time: 0.988 ms
- follow_up_tasks: Index Only Scan using ix_follow_up_tasks_due_status
- appointments: Seq Scan (14 rows — optimal for small tables)
- queue_entries: Seq Scan (7 rows — optimal for small tables)
- All buffer hits: shared hit=24 (all from cache, no disk I/O)
```

### Reporting Appointments Query (after indexes)
```
Execution Time: 0.545 ms
- HashAggregate on status, Seq Scan (optimal for 14 rows)
- All buffer hits: shared hit=1
```

Note: With small demo datasets, PostgreSQL's query planner correctly chooses Seq Scan over Index Scan. The indexes become critical at production scale (thousands of appointments per clinic).

---

## 5. Security Model Verification

### 5.1 RLS Tenant Isolation
- Every tenant-scoped transaction calls `set_tenant_context(db, clinic_id, user_id)` before queries
- Cached session path calls `apply_rls_config()` which sets `app.clinic_id` and `app.support_access_id` via `set_config(..., true)` (transaction-local)
- RLS policies filter on `current_setting('app.clinic_id')`
- Cache key is `token_hash` — each session belongs to exactly one clinic, so cache hits always apply correct RLS context

### 5.2 Cache Invalidation
- `revoke_session()` immediately evicts from `_session_cache`
- `consume_manual_reset()` calls `_session_cache.clear()` after revoking all sessions
- Permission changes propagate within 60s TTL (acceptable: role changes are rare admin actions)
- Cross-worker cache: each worker has independent cache; worst case is 30s stale session

### 5.3 Rate Limiting
- In-memory token bucket per (session_cookie, "global", is_write)
- GET: 200 req/min, Write: 60 req/min
- Per-worker limits (no cross-worker coordination — 4 workers means effective 800 GET/min per user)
- Returns 429 with Retry-After header

---

## 6. Queue 404 Investigation

**Finding**: Load test was hitting `/api/v1/queue` which does not exist. The queue endpoint lives at `/api/v1/operations/queue` (under the operations router with prefix `/api/v1/operations`).

**Root cause**: Test script URL mismatch, not a server bug.

**Resolution**: Corrected load test URLs.

---

## 7. Staff 404 Investigation

**Finding**: `/api/v1/staff` returns 404 because no bare GET endpoint is defined on the staff router. The actual staff list endpoint is `/api/v1/staff/users`.

**Root cause**: Test script URL mismatch. Staff router defines `/roles`, `/permissions`, `/users` but not a root GET handler.

---

## 8. Frontend Optimizations Applied

1. **Visibility-aware polling**: Dashboard (60s) and Queue (30s) pages skip API calls when tab is hidden
2. **Browser caching**: Expanded `CACHED_GETS` set to include dashboard-summary and reporting-summary (15s TTL); auth/me TTL increased from 10s to 30s
3. **Removed `cache: "no-store"`** from GET requests (kept only for mutations)
4. **Estimated reduction**: 30-50% fewer API calls from inactive browser tabs
