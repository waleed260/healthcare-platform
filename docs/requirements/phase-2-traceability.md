# Phase 2 traceability

Status: implemented pending PostgreSQL-backed exit-gate execution.

| Requirement | Evidence | Proof |
| --- | --- | --- |
| Tenant keys and canonical base fields | `migrations/versions/0001_tenant_foundation.py` | `clinics` and probe records use UUID, UTC timestamps, archive field, and version |
| Separate migration/runtime roles | `infra/docker/postgres-init/001-runtime-role.sql`, `infra/docker/compose.yml` | API receives runtime credentials; migrate service receives migrator credentials |
| Explicit tenant context | `app/db/tenant.py` | Transaction-local `app.clinic_id` and optional `app.user_id` setters |
| Forced RLS | `migrations/versions/0001_tenant_foundation.py` | `tenant_probe_records` has enabled and forced RLS with `USING` and `WITH CHECK` policy |
| Two-tenant isolation matrix start | `tests/test_tenant_isolation.py` | Runtime role sees only its context tenant and cannot insert another tenant's row |

The probe table is infrastructure test data only. Patient, appointment, and other clinical tables remain deferred to their ordered phases.

Authentication implementation begins in `apps/api/app/modules/identity/` and is tracked against AUT-003, AUT-012, and SEC-006. RBAC remains a separate stage.
