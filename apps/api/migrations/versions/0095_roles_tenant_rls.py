"""Enable tenant RLS on the roles table.

roles carries a clinic_id and the app creates clinic-custom roles
(staff create-role), yet the table had no RLS — a clinic-owned table
isolated only at the application layer. Enable + FORCE RLS:

- read: own-clinic rows, the shared global system roles (clinic_id IS NULL
  — e.g. 'owner'/'receptionist', read by the invitation and staff flows under
  tenant context), or a platform-admin context;
- write (insert/update/delete): own-clinic rows only, or platform-admin — so a
  clinic can manage ITS custom roles but can never mutate a global role or
  another clinic's role (a global-role UPDATE/DELETE from clinic context is
  simply filtered to zero rows by the write policy's USING clause).

The global system roles are seeded by EARLIER migrations (which run before this
one), so FORCE does not block seeding on a fresh database. The policies are
deliberately NOT named `%_tenant_policy`: the bulk safe-cast rewrites (0037,
0065) target that suffix and would replace this read policy with an own-only
one, dropping the global-role read the app depends on.
"""
from alembic import op


revision = "0095_roles_tenant_rls"
down_revision = "0094_integrity_guards"
branch_labels = None
depends_on = None

_OWN = "clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid"
_PLATFORM = "current_setting('app.is_platform_admin', true) = 'true'"


def upgrade() -> None:
    op.execute("ALTER TABLE roles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE roles FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY roles_tenant_read ON roles FOR SELECT "
        f"USING ({_OWN} OR clinic_id IS NULL OR {_PLATFORM})"
    )
    op.execute(
        f"CREATE POLICY roles_tenant_write ON roles FOR ALL "
        f"USING ({_OWN} OR {_PLATFORM}) WITH CHECK ({_OWN} OR {_PLATFORM})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS roles_tenant_write ON roles")
    op.execute("DROP POLICY IF EXISTS roles_tenant_read ON roles")
    op.execute("ALTER TABLE roles NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE roles DISABLE ROW LEVEL SECURITY")
