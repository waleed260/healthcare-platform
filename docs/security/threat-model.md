# Initial threat model

## Assets

Patient identity and appointment data, clinic content, staff sessions, private documents, and platform secrets.

## Trust boundaries

Public browser → Next.js; staff browser → Next.js with a future secure session; Next.js → FastAPI over HTTPS; FastAPI → PostgreSQL and storage using server-side credentials.

## Initial mitigations

- No patient or secret data exists in this Phase 1 shell.
- API exposes only health endpoints.
- The web shell contains no authentication claims or clinical records.
- Future clinic-owned tables must carry tenant context and forced PostgreSQL RLS before clinical expansion.
- Cookie-authenticated state-changing operations, CRM commands, and private-file mutations validate the allowed
  Origin and `X-CSRF-Token` before tenant-scoped authorization or writes (SEC-006).

## Required next review

Before Phase 2, approve the tenant context transaction mechanism, runtime/migration database roles, CSRF/CORS topology, and the two-tenant isolation test matrix.
