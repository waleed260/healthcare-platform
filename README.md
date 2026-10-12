# care/fully — Clinic CRM + Website SaaS

Multi-tenant platform for private clinics: scheduling, patient records, billing, clinical workflows, and a public marketing/booking website per clinic. Tenant isolation is enforced in the database via PostgreSQL Row-Level Security, not just application code.

## Architecture

```
apps/api          FastAPI backend (Python 3.12, SQLAlchemy Core, psycopg3)
apps/web          Next.js 16 / React 19 frontend
packages/contracts  Committed OpenAPI spec + generated TypeScript types
infra/            Docker stack, backup/restore, RLS verification, tunnel config
scripts/          Local dev setup, full verification pipeline
```

### Backend modules

identity, authorization, crm (patients/merge/care-team), appointments + scheduling, clinical + forms + tools + media, finance (invoices/payments/expenses/commissions), packages, catalog, staff, inventory, operations (queue/follow-ups/notifications), governance (privacy/audit/retention), files (documents with scan pipeline), websites + content + library, upgrades, blueprint_core.

### Security

Opaque hashed session tokens with idle/absolute expiry and rotation. Constant-time CSRF double-submit. Durable login rate limiting via independent transaction. MFA (TOTP + recovery codes) with encrypted-at-rest secrets. Upload magic-byte validation + hash-verified scans + quarantine. Production config fails closed on missing secrets, HTTPS origins, and storage backend.

## Quick start

### Local PostgreSQL

```bash
# Create the databases and roles
bash scripts/dev/setup-local-postgres.sh

# Run migrations
cd apps/api
alembic upgrade head
```

### Docker (self-hosted)

```bash
# Copy and edit environment
cp infra/docker/.env.example .env

# Start the full stack (Postgres, API, worker, web)
docker compose up --build
```

### Development

```bash
# API
cd apps/api
pip install -r requirements.txt
uvicorn app.main:app --reload

# Web
cd apps/web
npm install
npm run dev
```

## Verification

Run the full 10-phase evidence-gated pipeline:

```bash
bash scripts/verify-all.sh
```

This runs: migrations, seed verification (x2), RLS psql probe, API pytest, ESLint zero-warning, tsc, build, shuffled Playwright order, negative control, and optional Lighthouse.

### Individual checks

```bash
# API tests
cd apps/api && pytest

# Frontend type check + lint
cd apps/web && npx tsc --noEmit && npx eslint .

# Contract drift check
python3 packages/contracts/generate_types.py && git diff --exit-code packages/contracts/

# RLS contract verification
python3 infra/check_rls_contract.py

# Deployment smoke test
bash infra/verify_deploy.sh
```

## Deployment

The API runs behind a reverse proxy (ngrok static domain or Cloudflare tunnel). The web app deploys to Vercel with `API_URL` pointing to the API origin.

See `infra/TUNNEL.md` for tunnel configuration and `infra/docker/` for the production Docker setup.

## Project documentation

- `docs/project-summary.md` — full architecture and module reference
- `docs/PENDING_WORK_PLAN.md` — roadmap with phase tracking
- `docs/CRM_DEFECT_LEDGER.md` — known issues and their resolutions
- `docs/blueprint/adr/` — architecture decision records
