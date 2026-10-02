# Project summary — Clinic CRM + Website SaaS

- **Date:** 2026-10-03
- **Repo:** `waleed260/healthcare-platform`
- **Active branch:** `feat/lead-activities` → open as **PR #1** to `main`
- **Scope of codebase:** ~13.4k lines of API Python across 24 modules, 66 migrations, a Next.js 16 web app (~32 pages), a generated API contract, and a self-hostable Docker stack with CI.

---

## What it is

A multi-tenant SaaS for private clinics: one platform hosts many clinics, each with branches, specialties, staff/roles, patients, scheduling, clinical records, billing, and a public marketing/booking website. Tenant isolation is enforced in the database (PostgreSQL Row-Level Security keyed on `app.clinic_id`), not just in application code.

## Architecture

- **`apps/api`** — FastAPI backend (Python 3.12), SQLAlchemy Core over `text()` SQL, psycopg3 with a client-side cursor (so pooled/serverless Postgres and untyped-NULL keyset cursors work). Sessions are opaque tokens hashed at rest with idle/absolute expiry + rotation; CSRF is a double-submit token compared in constant time; writes require an allowed `Origin`.
- **`apps/web`** — Next.js 16 / React 19 app: authenticated clinic console (`/(authenticated)/…`), public per-clinic sites (`/[clinicSlug]/…`), booking (`/book/[clinicSlug]`), and a platform admin area (`/admin`).
- **`packages/contracts`** — committed `openapi.json` + generated `openapi-types.ts`; CI fails if either drifts from the code.
- **`infra` + `docker-compose.yml`** — self-hosted stack (Postgres + owner-run migrations + the API as a least-privilege runtime role + a media-scan worker + an optional Cloudflare tunnel), plus backup/restore, release-gate, RLS-contract and seed-verification tooling.

## Backend modules (`apps/api/app/modules`)

`identity` (auth, sessions, MFA/TOTP, invitations, Google sign-in) · `authorization` (RBAC permission checks) · `crm` (patients, contacts, notes, consents, care team, tags, duplicate detection, **merge**) · `appointments` + `scheduling` (availability, booking, state machine) · `clinical` + `clinical_forms` + `clinical_tools` + `clinical_media` (records, specialty forms/tools, patient before/after media) · `finance` (invoices, payments, expenses, commissions) · `packages` (patient packages/sessions) · `catalog` (services/specialties) · `staff` · `inventory` · `operations` (follow-ups, queue, notifications, web push) · `governance` (privacy requests, exports, retention, audit) · `audit` · `files` (private documents, magic-byte validation, hash-verified scan, quarantine, short-lived download tokens) · `websites` + `website_library` + `website_content` (site builder, reusable sections, SEO/redirects, forms, blog, testimonials) · `upgrades` · `blueprint_core`.

## Data & tenancy

- **66 Alembic migrations**, head `0066_clinical_tool_states`. Composite `(clinic_id, id)` keys and `(clinic_id, …)` foreign keys throughout; every tenant table has an RLS policy using a NULLIF-guarded `clinic_id` cast. A separate migration owner role applies DDL; the app runs as a restricted `healthcare_runtime` role whose grants CI verifies.
- Patient data spans 17 patient-scoped tables; the **patient-merge service** (`crm/merge.py`) holds the authoritative registry of them with a test that fails if a future table is added without being registered.

## Security posture

Tenant isolation in depth (transaction-local `set_config` + forced RLS + a self-check); opaque hashed session tokens with rotation; constant-time CSRF + origin checks on mutations; durable, independent-transaction login rate limiting with account lockout; upload magic-byte validation + hash-verified scans + quarantine + user-bound download tokens; public surfaces rate-limited, consent-gated, and `no-store` for patient media; production config fails closed (secrets, HTTPS origins, storage backend, and forwarded-IP trust all validated at startup).

## Testing & CI

- **250 API tests pass, 2 skipped** (storage/supabase config-gated). Unit tests run without a DB; ~24 integration tests run against a real PostgreSQL (tenant isolation, RBAC, CRM scope, login lockout, patient merge, merge reconciliation, etc.).
- `tsc --noEmit` clean; ESLint 0 errors (3 pre-existing `<img>` warnings).
- **CI (`.github/workflows/ci.yml`)** runs on push + PR: API tests on a Postgres service, dependency audit, secret scan, OpenAPI/TS contract drift check, offline-migration + downgrade check, seed + runtime-RLS verification; web lint/tsc/build + Playwright e2e (booking concurrency, tenant isolation, RBAC, core workflow) + a negative-control isolation test + a Lighthouse mobile gate; a full `docker compose` stack boot with an API smoke test; and image builds.

## Current branch / PR status

`feat/lead-activities` is one logical change ahead of `main`, open as **PR #1** (3 commits), **mergeable (no conflicts)**. It verifies and fixes a multi-LLM review (`docs/claim-verification-2026-10-02.md`):

1. **Durable login lockout** — failures now commit on an independent session (previously erased by the login rollback; the lock was dead code).
2. **Complete patient merge** — a central service repoints all 17 patient-scoped tables with explicit conflict rules, tombstones the source, and audits the merge (previously orphaned documents, media, invoices, packages, clinical forms/tools, prescriptions).
3. **A latent `duplicate_candidates` bug** neither reviewer caught (non-f-string SQL → runtime syntax error).
4. **Hardening** — `no-store` for public patient media; configurable forwarded-IP trust with a production guard against wildcards; ILIKE wildcard escaping; patient-number collision retry; constant-time CSRF; origin validation on login + duplicate-candidates; provider validation.
5. **Pagination** of the high-volume patient lists (media, notes) + bounded caps on care-team/history.
6. **MFA** cookie-before-commit ordering.
7. **A read-only merge-reconciliation job** (`scripts/reconcile_merges.py`) to find data orphaned by any merges run on the old code.

## Open items / recommendations

- **Merge PR #1** once CI is green and a human has reviewed the security-sensitive changes (merge decision intentionally left to a person).
- **Run `reconcile_merges.py` against a production backup** if any patient merges were performed before this fix shipped — code alone does not heal already-orphaned rows.
- **Frontend "load more"** wiring for the now-paginated media/notes views (the API exposes `next_cursor`; current views show the first page, which is a generous 100/200 cap). A small follow-up, not a regression for realistic data volumes.
- **Secrets are clean**: `.env`, `.env.save`, `docker.env` are git-ignored (mode 0600) and never committed; CI's secret scan enforces this.
