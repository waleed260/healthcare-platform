# Healthcare Platform

Secure, tenant-aware foundation for a multi-tenant clinic website, appointment,
CRM, and operations platform. The repository is still pre-production: later
phase exit gates and infrastructure integrations remain open.

## Repository layout

- `apps/web` — Next.js public site and authenticated dashboard shell
- `apps/api` — FastAPI modular monolith shell
- `packages/contracts` — shared API contract artifacts
- `packages/design-tokens` — shared visual tokens
- `infra/docker` — local container definitions
- `docs` — requirements, ADRs, UX flows, security, and runbooks

## Local development

```bash
docker compose -f infra/docker/compose.yml up --build
```

Then open `http://localhost:3000`, `http://localhost:8000/health`, or `http://localhost:8000/docs`.

To initialize the local PostgreSQL schema, run the migration service after the database is healthy:

```bash
docker compose -f infra/docker/compose.yml run --rm migrate
```

The API uses the restricted `healthcare_runtime` role. Alembic uses the separate `healthcare_migrator` role. Set `TEST_ADMIN_DATABASE_URL` and `TEST_DATABASE_URL` to run the two-tenant isolation test against PostgreSQL.

The current branch contains ordered Phase 0–12 vertical slices, including
PostgreSQL migrations with forced RLS, opaque sessions/MFA, RBAC, scheduling,
CRM, private-file scanning, website publishing, operations, and governance.
Use `docs/implementation-roadmap.md` and the phase traceability documents for
implemented scope and explicit remaining work. No real patient data is included.

The web image in `apps/web/Dockerfile` is a production standalone image. Local
Compose uses `Dockerfile.dev` with hot reload; production builds pass the
container-reachable API origin through the `API_URL` build argument.
