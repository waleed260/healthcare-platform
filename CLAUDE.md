# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

**care/fully** — multi-tenant clinic CRM + website SaaS. PostgreSQL Row-Level Security enforces tenant isolation at the database layer, not just in application code. Every data-mutating query runs inside a transaction with `set_config('app.clinic_id', ...)` set via `app.db.tenant.set_tenant_context`.

## Architecture

- **apps/api** — FastAPI backend (Python 3.12, SQLAlchemy Core, psycopg3, Alembic migrations). No ORM models; queries use `sqlalchemy.text()` with raw SQL.
- **apps/web** — Next.js 16 / React 19 frontend (TypeScript 6, App Router). Uses `output: "standalone"` and rewrites `/api/*` to the backend via `API_URL`.
- **packages/contracts** — OpenAPI spec + generated TypeScript types. Run `python3 packages/contracts/generate_types.py` and verify no drift with `git diff --exit-code packages/contracts/`.
- **infra/** — Docker stack, RLS verification, tunnel config, backup/restore.

### Backend module layout

Each module under `apps/api/app/modules/<name>/` typically has: `routes.py` (FastAPI router), `schemas.py` (Pydantic models), `service.py` (business logic). Some add `merge.py`, `admin_routes.py`, etc. Routes import auth helpers (`_session_or_401`, `_validate_origin`, `verify_csrf`) from `identity.routes` and permission checks from `authorization.service.require_permission`.

### Module cross-references

- **blueprint_core** contains invoices, payments, and refund CRUD. Finance routes import `_authorized`, `_write_authorized`, and `invoice_receipt` from `blueprint_core.routes`.
- **catalog** (`/api/v1/services`, `/api/v1/branches`, `/api/v1/doctors`) manages the clinic's service catalog, branch-service and doctor-service assignments, rooms, resources, holidays, and service templates.
- **encounters** reference services via `administered_treatments[].service_id` and inventory via `administered_treatments[].inventory_product_id` and `medications[].inventory_product_id`.
- **finance** provides cashier summary, expenses, commissions, and provider revenue — all derived from the invoices/payments in blueprint_core.

### Frontend patterns

- API client: `apps/web/app/(authenticated)/_lib/client.ts` — `api<T>()` and `apiPage<T>()` with auto CSRF refresh and session-expiry redirect.
- Shared UI: drawers, toast, confirm dialog, pagination, clinic context all live in `_lib/`.
- Next.js 16 has breaking changes — read `apps/web/node_modules/next/dist/docs/` before writing frontend code.
- CSP nonces injected in `middleware.ts`; `ngrok-skip-browser-warning` header auto-added for API proxying.

### Security model

Session auth via opaque hashed tokens (not JWT). CSRF double-submit with `X-CSRF-Token` header. Authorization is role+permission based checked with `require_permission(db, user_id, clinic_id, "permission.code")`. MFA (TOTP) support with encrypted-at-rest secrets. File uploads validated by magic bytes.

### Clinical workflow chain

**Inventory** → **Services** → **Encounters** → **Billing** → **Finance**. Encounters reference services (via `service_id` on treatments/procedures) and inventory products (via `inventory_product_id` on treatments/medications). Billing creates invoices from encounter data. Finance aggregates billing data for cashier summaries and provider revenue.

## Common commands

### API (from `apps/api/`)

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload          # dev server on :8000
pytest                                  # all tests
pytest tests/test_crm_audit_integration.py  # single test file
pytest -k test_merge                    # tests matching pattern
alembic upgrade head                    # run migrations
alembic revision -m "description"       # create migration
```

Tests marked `@pytest.mark.integration` require a PostgreSQL `healthcare_test` database (see `scripts/dev/setup-local-postgres.sh`). Ruff is configured at 100-char line length, Python 3.12 target.

### Web (from `apps/web/`)

```bash
npm install
npm run dev                             # dev server on :3000
npx tsc --noEmit                        # type check
npx eslint .                            # lint (zero warnings required)
npx playwright test                     # e2e tests (builds first)
npx playwright test tests/crm-workflow.spec.ts  # single e2e spec
```

### From repo root

```bash
npm run dev:web                         # workspace shortcut for web dev
npm run build:web                       # workspace shortcut for web build
bash scripts/verify-all.sh              # full 10-phase verification pipeline
```

### Docker (full stack)

```bash
docker compose up --build               # Postgres + migrations + API + worker + web
docker compose --profile ngrok up -d    # with stable ngrok tunnel
```

### Contract drift check

```bash
python3 packages/contracts/generate_types.py && git diff --exit-code packages/contracts/
```

### RLS verification

```bash
python3 infra/check_rls_contract.py
```

## Database

Two PostgreSQL roles: `healthcare_migrator` (owns schema, runs Alembic) and `healthcare_runtime` (least-privilege, used by the app). Alembic reads `DATABASE_MIGRATION_URL` for migrations. The runtime connection uses `DATABASE_URL`. Tenant isolation: every tenant-scoped transaction calls `set_tenant_context(db, clinic_id, user_id)` before queries; RLS policies filter on `current_setting('app.clinic_id')`.

## Deployment

API runs behind a reverse proxy (ngrok static domain or Cloudflare tunnel). Web deploys to Vercel with `API_URL` env var pointing to the API origin. See `infra/TUNNEL.md`.

## Key conventions

- Backend returns `{"data": ...}` envelopes; errors use `{"error": {"code": "...", "message": "...", "fields": {...}}}`.
- Cursor-based pagination throughout (not offset); cursors are opaque base64-encoded strings.
- ESLint must pass with zero warnings for the web app.
- The `apps/web/AGENTS.md` file is auto-generated by `next dev` — don't try to remove it from diffs.

## Project docs

- `docs/project-summary.md` — full architecture and module reference.
- `docs/PENDING_WORK_PLAN.md` — roadmap with phase tracking.
- `docs/CRM_DEFECT_LEDGER.md` — known issues and their resolutions.
- `docs/blueprint/adr/` — architecture decision records.

---

## Operational rules

These rules govern how Claude Code sessions operate in this repository. They persist across sessions, context compactions, and resumed tasks.

### Session startup

At the start of every session:

1. Read this `CLAUDE.md`.
2. Read `.claude/WORK_STATE.md` if it exists.
3. Run `git status` and `git log --oneline -5`.
4. Identify completed, incomplete, and blocked tasks.
5. Continue from the exact next unfinished action — do not restart completed work.

Never assume work is done because a prior message claimed completion. Verify against actual file and git state.

### Implementation priority

The priority order is: understand the problem → reproduce it → find root cause → select architecture-compatible fix → implement → verify real behavior → review regressions → record evidence.

Do not stop after producing a plan or report. When the user requests a fix, implement it.

### Verification standard

A success toast, HTTP 200, frontend build, or mocked test is not proof of correctness.

For create/update/delete operations, verify: the API request → backend execution → database commit → fresh retrieval → resulting frontend state → persistence after reload.

If the operation did not persist, mark it FAIL and investigate. Never fabricate test results or claim untested work is complete.

### Fix loop

For each defect: **REPRODUCE → DIAGNOSE → CONFIRM ROOT CAUSE → IMPLEMENT → TEST → VERIFY DATABASE → CHALLENGE → REPEAT IF NEEDED.**

If the same fix fails twice, widen the investigation to shared services, transactions, caching, and authorization before retrying.

### Work state checkpoint

Maintain `.claude/WORK_STATE.md` — update it after completing a significant stage, discovering a blocker, or before ending a session. Contents:

1. Current task and objective.
2. Completed work with evidence.
3. Files changed.
4. Tests run and results (PASS/FAIL/BLOCKED/NOT RUN).
5. Unresolved defects.
6. Exact next action.

Never store passwords, database URLs, tokens, or patient data in the checkpoint.

### Data integrity (never cut)

Always preserve: authentication, authorization, role permissions, clinic/tenant isolation, branch-level access, database transactions, inventory ledger integrity, financial record integrity, patient-data confidentiality, audit history.

Never use fake success responses, hardcoded records, insecure permission shortcuts, or destructive database shortcuts. Do not use production data for destructive testing.

### Efficiency

- Read existing reports before creating new ones.
- Use focused tests after small changes; integration tests after module changes; full regression at final verification.
- Do not re-scan the entire repository when architecture is established.
- Do not regenerate unchanged files or repeat passing tests without reason.
- Keep progress messages short. Spend effort on code and verification, not narration.

### Completion reports

When reporting completion, include: what changed, root cause, files modified, tests run, actual results, remaining blockers, whether changes were committed/pushed. Use PASS/FAIL/BLOCKED/NOT RUN accurately. Do not declare completion while critical acceptance criteria remain unresolved.
