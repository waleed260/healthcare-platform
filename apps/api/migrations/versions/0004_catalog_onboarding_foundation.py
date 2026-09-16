"""Create clinic hours, holidays, doctors, services, and resources."""
from alembic import op
import sqlalchemy as sa

revision = "0004_catalog_onboarding_foundation"
down_revision = "0003_rbac_branch_scopes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    permissions = [
        ("doctor.read", "Read doctor profiles"),
        ("doctor.manage", "Manage doctor profiles"),
        ("service.read", "Read services"),
        ("service.manage", "Manage services"),
        ("schedule.read", "Read schedules and hours"),
        ("schedule.manage", "Manage schedules and hours"),
    ]
    for code, description in permissions:
        op.execute(sa.text("INSERT INTO permissions (code, description) VALUES (:code, :description) ON CONFLICT (code) DO NOTHING").bindparams(code=code, description=description))
    for role in ("owner", "manager"):
        op.execute(sa.text("""
            INSERT INTO role_permissions (role_id, permission_code)
            SELECT r.id, p.code FROM roles r CROSS JOIN permissions p
            WHERE r.name = :role AND p.code IN ('doctor.read', 'doctor.manage', 'service.read', 'service.manage', 'schedule.read', 'schedule.manage')
        """).bindparams(role=role))
    for role in ("doctor", "receptionist"):
        op.execute(sa.text("""
            INSERT INTO role_permissions (role_id, permission_code)
            SELECT r.id, p.code FROM roles r CROSS JOIN permissions p
            WHERE r.name = :role AND p.code IN ('doctor.read', 'service.read', 'schedule.read')
        """).bindparams(role=role))

    op.execute("""
        CREATE TABLE branch_hours (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            branch_id uuid NOT NULL,
            weekday smallint NOT NULL CHECK (weekday BETWEEN 0 AND 6),
            opens_at time NULL,
            closes_at time NULL,
            is_closed boolean NOT NULL DEFAULT false,
            breaks jsonb NOT NULL DEFAULT '[]'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_branch_hours_day UNIQUE (clinic_id, branch_id, weekday),
            CONSTRAINT fk_branch_hours_branch_tenant FOREIGN KEY (clinic_id, branch_id) REFERENCES branches (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE clinic_holidays (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            holiday_date date NOT NULL,
            name text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_clinic_holidays_date UNIQUE (clinic_id, holiday_date)
        )
    """)
    op.execute("""
        CREATE TABLE doctor_profiles (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            user_id uuid NULL,
            public_name text NOT NULL,
            specialty text NULL,
            registration text NULL,
            verification_status text NOT NULL DEFAULT 'unverified',
            bio text NULL,
            consultation_duration_minutes integer NOT NULL DEFAULT 30 CHECK (consultation_duration_minutes > 0),
            status text NOT NULL DEFAULT 'active',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz NULL,
            version integer NOT NULL DEFAULT 1,
            CONSTRAINT uq_doctor_profiles_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT fk_doctor_profiles_user_tenant FOREIGN KEY (clinic_id, user_id) REFERENCES users (clinic_id, id) ON DELETE SET NULL
        )
    """)
    op.execute("""
        CREATE TABLE services (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            name text NOT NULL,
            category text NULL,
            short_description text NULL,
            full_description text NULL,
            duration_minutes integer NOT NULL CHECK (duration_minutes > 0),
            buffer_before_minutes integer NOT NULL DEFAULT 0 CHECK (buffer_before_minutes >= 0),
            buffer_after_minutes integer NOT NULL DEFAULT 0 CHECK (buffer_after_minutes >= 0),
            price_mode text NOT NULL DEFAULT 'contact',
            amount_minor integer NULL CHECK (amount_minor >= 0),
            currency char(3) NULL,
            approval_mode text NOT NULL DEFAULT 'staff_approval',
            visibility text NOT NULL DEFAULT 'public',
            status text NOT NULL DEFAULT 'active',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz NULL,
            version integer NOT NULL DEFAULT 1,
            CONSTRAINT uq_services_clinic_id UNIQUE (clinic_id, id)
        )
    """)
    op.execute("""
        CREATE TABLE doctor_services (
            clinic_id uuid NOT NULL,
            doctor_id uuid NOT NULL,
            service_id uuid NOT NULL,
            PRIMARY KEY (clinic_id, doctor_id, service_id),
            FOREIGN KEY (clinic_id, doctor_id) REFERENCES doctor_profiles (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, service_id) REFERENCES services (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE branch_doctors (
            clinic_id uuid NOT NULL,
            branch_id uuid NOT NULL,
            doctor_id uuid NOT NULL,
            PRIMARY KEY (clinic_id, branch_id, doctor_id),
            FOREIGN KEY (clinic_id, branch_id) REFERENCES branches (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, doctor_id) REFERENCES doctor_profiles (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE branch_services (
            clinic_id uuid NOT NULL,
            branch_id uuid NOT NULL,
            service_id uuid NOT NULL,
            PRIMARY KEY (clinic_id, branch_id, service_id),
            FOREIGN KEY (clinic_id, branch_id) REFERENCES branches (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, service_id) REFERENCES services (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE rooms (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            branch_id uuid NOT NULL,
            name text NOT NULL,
            status text NOT NULL DEFAULT 'active',
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_rooms_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT uq_rooms_branch_name UNIQUE (clinic_id, branch_id, name),
            FOREIGN KEY (clinic_id, branch_id) REFERENCES branches (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE resources (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            branch_id uuid NOT NULL,
            name text NOT NULL,
            capacity integer NOT NULL DEFAULT 1 CHECK (capacity > 0),
            status text NOT NULL DEFAULT 'active',
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_resources_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT uq_resources_branch_name UNIQUE (clinic_id, branch_id, name),
            FOREIGN KEY (clinic_id, branch_id) REFERENCES branches (clinic_id, id) ON DELETE CASCADE
        )
    """)

    for table in ("branch_hours", "clinic_holidays", "doctor_profiles", "services", "doctor_services", "branch_doctors", "branch_services", "rooms", "resources"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(sa.text(f"""
            CREATE POLICY {table}_tenant_policy ON {table}
            USING (clinic_id = current_setting('app.clinic_id', true)::uuid)
            WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)
        """))
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON branch_hours, clinic_holidays, doctor_profiles, services, doctor_services, branch_doctors, branch_services, rooms, resources TO healthcare_runtime")


def downgrade() -> None:
    for table in ("resources", "rooms", "branch_services", "branch_doctors", "doctor_services", "services", "doctor_profiles", "clinic_holidays", "branch_hours"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
