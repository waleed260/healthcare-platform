# ADR-0001: Phase 1 foundation

- Status: accepted for implementation
- Requirements: Phase 0, Phase 1, WEB-*, UX-003

## Decision

Start with a single repository containing a Next.js web app and a FastAPI modular-monolith API. Keep the first runnable slice dependency-light: health/readiness endpoints, public website shell, dashboard shell, Docker Compose, and CI.

## Consequences

The shell is intentionally not connected to a database and cannot process clinical data. Database access, tenant context, RLS, sessions, and permissions begin only after the Phase 1 exit gate and in the ordered phases defined by the implementation specification.

## Rejected shortcuts

No client-only authorization, generic clinical API, local patient fixtures, or placeholder external messaging integration is introduced.
