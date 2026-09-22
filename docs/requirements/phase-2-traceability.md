# Phase 2 traceability

Status: implemented pending PostgreSQL-backed exit-gate execution.

| Requirement | Evidence | Proof |
| --- | --- | --- |
| Tenant keys and canonical base fields | `migrations/versions/0001_tenant_foundation.py` | `clinics` and probe records use UUID, UTC timestamps, archive field, and version |
| Separate migration/runtime roles | `infra/docker/postgres-init/001-runtime-role.sql`, `infra/docker/compose.yml` | API receives runtime credentials; migrate service receives migrator credentials |
| Explicit tenant context | `app/db/tenant.py` | Transaction-local `app.clinic_id` and optional `app.user_id` setters |
| Forced RLS and composite tenant relationships | Migrations `0001`–`0045`, plus `tests/test_tenant_isolation.py::test_required_clinic_tables_have_forced_rls` | Required patient, appointment, operations, CRM, privacy/export, background-job, catalog, scheduling, files, and website tables are asserted to have enabled/forced RLS and at least one tenant policy in the PostgreSQL CI service; `0045_access_token_tenant_fk.py` protects clinic-scoped access-token users with a composite tenant FK; global platform tables such as plans and system announcements are intentionally outside this tenant set |
| Two-tenant isolation matrix start | `tests/test_tenant_isolation.py` | Runtime role sees only its context tenant and cannot insert another tenant's row |

The probe table is infrastructure test data only. The named-table RLS contract
is now checked as part of the ordered clinical isolation matrix; local runs
skip these PostgreSQL assertions when integration URLs are not configured.

Authentication implementation begins in `apps/api/app/modules/identity/` and is tracked against AUT-003, AUT-012, and SEC-006. RBAC remains a separate stage.
