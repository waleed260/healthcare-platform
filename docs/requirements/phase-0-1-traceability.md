# Phase 0/1 traceability

Status: foundation in progress — no unresolved product decision is introduced by this slice.

| Requirement | Evidence | Exit condition |
| --- | --- | --- |
| Phase 0 / ADRs, requirements map, threat model, UX flows | `docs/adr/`, `docs/security/`, `docs/ux/` | Decisions and flows are recorded before clinical modules |
| Phase 1 / monorepo | `apps/`, `packages/`, `infra/`, `docs/` | Repository contract exists |
| Phase 1 / FastAPI shell | `apps/api/app/main.py` | `/health`, `/ready`, `/api/v1/health` return JSON |
| Phase 1 / Next.js shell | `apps/web/app/` | Public and dashboard routes render responsively |
| Phase 1 / test harness | `apps/api/tests/`, `.github/workflows/ci.yml` | API smoke tests and web build are CI commands |
| Phase 1 / Docker | `infra/docker/compose.yml` | Web and API services can run locally |

Deferred by the ordered plan: PostgreSQL schema/RLS, authentication, RBAC, clinical workflows, storage, and real patient data.
