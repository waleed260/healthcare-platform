"""Create permissions, roles, branches, and branch scopes."""
from alembic import op
import sqlalchemy as sa

revision = "0003_rbac_branch_scopes"
down_revision = "0002_identity_authentication"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD CONSTRAINT uq_users_clinic_id UNIQUE (clinic_id, id)")
    op.execute("""
        CREATE TABLE branches (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE RESTRICT,
            code text NOT NULL,
            name text NOT NULL,
            timezone text NOT NULL DEFAULT 'UTC',
            address jsonb NOT NULL DEFAULT '{}'::jsonb,
            phone text NULL,
            status text NOT NULL DEFAULT 'active',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz NULL,
            version integer NOT NULL DEFAULT 1,
            CONSTRAINT uq_branches_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT uq_branches_clinic_code UNIQUE (clinic_id, code)
        )
    """)
    op.execute("""
        CREATE TABLE permissions (
            code text PRIMARY KEY,
            description text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE roles (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NULL REFERENCES clinics(id) ON DELETE CASCADE,
            name text NOT NULL,
            is_system boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_roles_clinic_name UNIQUE (clinic_id, name)
        )
    """)
    op.execute("""
        CREATE TABLE role_permissions (
            role_id uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            permission_code text NOT NULL REFERENCES permissions(code) ON DELETE CASCADE,
            PRIMARY KEY (role_id, permission_code)
        )
    """)
    op.execute("""
        CREATE TABLE user_roles (
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            user_id uuid NOT NULL,
            role_id uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            assigned_by uuid NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (clinic_id, user_id, role_id),
            CONSTRAINT fk_user_roles_user_tenant FOREIGN KEY (clinic_id, user_id) REFERENCES users (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE user_branch_scopes (
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            user_id uuid NOT NULL,
            branch_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (clinic_id, user_id, branch_id),
            CONSTRAINT fk_user_branch_scopes_user_tenant FOREIGN KEY (clinic_id, user_id) REFERENCES users (clinic_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_user_branch_scopes_branch_tenant FOREIGN KEY (clinic_id, branch_id) REFERENCES branches (clinic_id, id) ON DELETE CASCADE
        )
    """)

    permissions = [
        ("clinic.read", "Read clinic configuration"),
        ("clinic.update", "Update clinic configuration"),
        ("staff.read", "Read staff records"),
        ("staff.manage", "Manage staff records and roles"),
        ("audit.read", "Read audit events"),
    ]
    for code, description in permissions:
        op.execute(sa.text("INSERT INTO permissions (code, description) VALUES (:code, :description)").bindparams(code=code, description=description))
    for name in ("owner", "manager", "doctor", "receptionist", "website_editor"):
        op.execute(sa.text("INSERT INTO roles (name, is_system) VALUES (:name, true)").bindparams(name=name))
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_code)
        SELECT r.id, p.code
        FROM roles r CROSS JOIN permissions p
        WHERE r.name = 'owner'
    """)
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_code)
        SELECT r.id, p.code
        FROM roles r JOIN permissions p ON p.code IN ('clinic.read', 'staff.read', 'audit.read')
        WHERE r.name = 'manager'
    """)
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_code)
        SELECT r.id, p.code
        FROM roles r JOIN permissions p ON p.code = 'clinic.read'
        WHERE r.name IN ('doctor', 'receptionist', 'website_editor')
    """)

    op.execute("ALTER TABLE branches ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE branches FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY branches_tenant_policy ON branches
        USING (clinic_id = current_setting('app.clinic_id', true)::uuid)
        WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)
    """)
    op.execute("ALTER TABLE user_roles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE user_roles FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY user_roles_tenant_policy ON user_roles
        USING (clinic_id = current_setting('app.clinic_id', true)::uuid)
        WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)
    """)
    op.execute("ALTER TABLE user_branch_scopes ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE user_branch_scopes FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY user_branch_scopes_tenant_policy ON user_branch_scopes
        USING (clinic_id = current_setting('app.clinic_id', true)::uuid)
        WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)
    """)
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON branches, permissions, roles, role_permissions, user_roles, user_branch_scopes TO healthcare_runtime")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_branch_scopes")
    op.execute("DROP TABLE IF EXISTS user_roles")
    op.execute("DROP TABLE IF EXISTS role_permissions")
    op.execute("DROP TABLE IF EXISTS roles")
    op.execute("DROP TABLE IF EXISTS permissions")
    op.execute("DROP TABLE IF EXISTS branches")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS uq_users_clinic_id")
