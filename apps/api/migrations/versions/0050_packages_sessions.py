"""Add package definitions, patient purchases, and session consumption ledger."""
from alembic import op
import sqlalchemy as sa

revision = "0050_packages_sessions"
down_revision = "0049_reporting_permission"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for code, description in (("package.read", "Read treatment packages"), ("package.manage", "Manage treatment packages"), ("package.override", "Override package session limits")):
        op.execute(sa.text("INSERT INTO permissions (code, description) VALUES (:code, :description) ON CONFLICT (code) DO NOTHING").bindparams(code=code, description=description))
    roles = {"owner": ("package.read", "package.manage", "package.override"), "manager": ("package.read", "package.manage", "package.override"), "doctor": ("package.read",), "receptionist": ("package.read",)}
    for role, codes in roles.items():
        for code in codes:
            op.execute(sa.text("INSERT INTO role_permissions (role_id, permission_code) SELECT r.id, :code FROM roles r WHERE r.name = :role ON CONFLICT DO NOTHING").bindparams(role=role, code=code))
    op.execute("""
        CREATE TABLE package_definitions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            specialty_id uuid NULL,
            name text NOT NULL,
            description text NULL,
            total_price_minor integer NOT NULL CHECK (total_price_minor >= 0),
            original_value_minor integer NULL CHECK (original_value_minor IS NULL OR original_value_minor >= total_price_minor),
            currency char(3) NOT NULL,
            validity_days integer NOT NULL CHECK (validity_days > 0),
            status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz NULL,
            CONSTRAINT uq_package_definitions_clinic_id UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id) REFERENCES clinics (id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, specialty_id) REFERENCES clinic_specialties (clinic_id, specialty_id) ON DELETE RESTRICT
        )
    """)
    op.execute("""
        CREATE TABLE package_services (
            clinic_id uuid NOT NULL,
            package_definition_id uuid NOT NULL,
            service_id uuid NOT NULL,
            sessions_count integer NOT NULL CHECK (sessions_count > 0),
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (clinic_id, package_definition_id, service_id),
            FOREIGN KEY (clinic_id, package_definition_id) REFERENCES package_definitions (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, service_id) REFERENCES services (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    op.execute("""
        CREATE TABLE patient_packages (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            patient_id uuid NOT NULL,
            package_definition_id uuid NOT NULL,
            invoice_id uuid NULL,
            purchased_at timestamptz NOT NULL DEFAULT now(),
            expires_at timestamptz NOT NULL,
            status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'expired', 'exhausted', 'cancelled')),
            total_sessions integer NOT NULL CHECK (total_sessions > 0),
            used_sessions integer NOT NULL DEFAULT 0 CHECK (used_sessions >= 0),
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_patient_packages_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_patient_packages_used CHECK (used_sessions >= 0 AND used_sessions <= total_sessions),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES patients (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, package_definition_id) REFERENCES package_definitions (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, invoice_id) REFERENCES invoices (clinic_id, id) ON DELETE SET NULL
        )
    """)
    op.execute("""
        CREATE TABLE package_sessions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            patient_package_id uuid NOT NULL,
            service_id uuid NULL,
            appointment_id uuid NULL,
            status text NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'used', 'void', 'overuse_override')),
            override_reason text NULL,
            used_at timestamptz NULL,
            used_by_user_id uuid NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_package_sessions_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_package_session_override CHECK (status <> 'overuse_override' OR NULLIF(trim(override_reason), '') IS NOT NULL),
            FOREIGN KEY (clinic_id, patient_package_id) REFERENCES patient_packages (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, service_id) REFERENCES services (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, appointment_id) REFERENCES appointments (clinic_id, id) ON DELETE SET NULL,
            FOREIGN KEY (clinic_id, used_by_user_id) REFERENCES users (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    for table in ("package_definitions", "package_services", "patient_packages", "package_sessions"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(sa.text(f"CREATE POLICY {table}_tenant_policy ON {table} USING (clinic_id = current_setting('app.clinic_id', true)::uuid) WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)"))
    op.execute("CREATE INDEX ix_package_definitions_clinic_status ON package_definitions (clinic_id, status, name)")
    op.execute("CREATE INDEX ix_patient_packages_patient ON patient_packages (clinic_id, patient_id, status, expires_at)")
    op.execute("CREATE INDEX ix_package_sessions_package ON package_sessions (clinic_id, patient_package_id, status, created_at)")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON package_definitions, package_services, patient_packages, package_sessions TO healthcare_runtime")


def downgrade() -> None:
    for table in ("package_sessions", "patient_packages", "package_services", "package_definitions"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
