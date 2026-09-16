# Phase 4 RBAC traceability

| Requirement | Evidence |
| --- | --- |
| Backend-enforced permissions | `app/modules/authorization/service.py`, `/api/v1/clinic/context` |
| Permission catalog | `app/modules/authorization/permissions.py`, migration seed data |
| Tenant-bound role assignments | `user_roles` composite tenant foreign key and forced RLS |
| Branch scopes | `branches`, `user_branch_scopes`, composite tenant foreign keys and scope-aware authorization query |
| Staff role/permission discovery | `GET /api/v1/staff/roles`, `GET /api/v1/staff/permissions`, restricted by `staff.read` |
| Security headers | `app/main.py` request middleware |
| Production fail-closed configuration | `app/core/config.py` production validator |
| Isolation tests | `tests/test_rbac_isolation.py` and CI PostgreSQL service |

The role catalog is intentionally small in this stage. Clinical permissions are added with their owning domain modules so every command can carry its object scope and audit behavior.

Clinic configuration now has versioned update and lifecycle commands in
`app/modules/authorization/routes.py`; suspension/archival revokes staff sessions
and public appointment-management tokens. Staff users have dedicated status,
invitation-revocation, role-assignment, and branch-scope commands with tenant
checks and audit events. Every successful role or branch-scope mutation also
revokes the affected user's active sessions, forcing re-authentication before
the changed privilege set can be used. Role and branch-scope grants are limited
to active, non-archived staff and active, non-archived branches at the database
command boundary.
