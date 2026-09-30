# Repository Guidelines

## Project Structure & Module Organization

- `apps/web/` contains the Next.js 16 frontend, public pages, authenticated clinic/admin surfaces, and Playwright tests.
- `apps/api/` contains the FastAPI modular monolith, Alembic migrations, domain modules, and pytest tests.
- `packages/contracts/` holds OpenAPI artifacts and generated shared types; `packages/design-tokens/` holds visual tokens.
- `infra/` contains Docker, PostgreSQL initialization, backup/restore, worker, and performance tooling.
- `docs/` is the source of truth for requirements, ADRs, UX flows, security, runbooks, and release evidence.

## Build, Test, and Development Commands

```bash
npm run dev:web                         # Start the web app with hot reload
npm run build:web                       # Create a production web build
npm run lint:web                        # Run ESLint for the web app
cd apps/api && .venv/bin/python -m pytest -q  # Run API unit tests
cd apps/web && npm run test:e2e         # Run Playwright browser tests
bash scripts/verify-all.sh              # Full PostgreSQL, API, web, and browser verification
docker compose -f infra/docker/compose.yml up --build  # Start local services
```

Run `scripts/dev/setup-local-postgres.sh` and configure the documented database variables before database-backed tests or `verify-all.sh`.

## Coding Style & Naming Conventions

Use four-space indentation for Python and project-standard TypeScript formatting. Python targets 3.12 with a 100-character Ruff line limit; use `snake_case` for Python modules/functions and `camelCase` for TypeScript variables/functions. Keep FastAPI code inside the relevant `apps/api/app/modules/<domain>/` module. Preserve tenant context, RLS, permission checks, CSRF, audit, and version-locking patterns in new changes.

## Testing Guidelines

Name Python tests `test_*.py` and test functions `test_*`. Keep unit tests near the affected domain and mark PostgreSQL-dependent tests with the configured `integration` marker. Add or update Playwright specs for user-visible workflows, including responsive and accessibility coverage where relevant. Run focused tests first, then the full verification script for cross-tenant or release-sensitive changes.

## Commit & Pull Request Guidelines

Use concise Conventional Commit-style subjects such as `fix(web): ...`, `test(web): ...`, or `docs: ...`. PRs should explain the behavior and scope, link the relevant requirement/ADR, list verification commands, and include screenshots or recordings for UI changes. Call out migrations, security-impacting changes, tenant-isolation implications, and any remaining release-gate evidence.

## Security & Configuration

Never commit secrets or real patient data. Keep migration and runtime database roles separate. Treat tenant isolation, forced RLS, server-side authorization, MFA/session handling, private file scanning, and auditability as non-negotiable boundaries.
