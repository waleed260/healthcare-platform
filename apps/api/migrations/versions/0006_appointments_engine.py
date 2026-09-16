"""Create patients and the concurrency-safe appointment engine."""
from alembic import op
import sqlalchemy as sa

revision = "0006_appointments_engine"
down_revision = "0005_website_builder"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    for code, description in (("appointment.read", "Read appointments"), ("appointment.create", "Create appointments"), ("appointment.manage", "Manage appointment lifecycle")):
        op.execute(sa.text("INSERT INTO permissions (code, description) VALUES (:code, :description) ON CONFLICT (code) DO NOTHING").bindparams(code=code, description=description))
    for role in ("owner", "manager", "doctor", "receptionist"):
        op.execute(sa.text("""
            INSERT INTO role_permissions (role_id, permission_code)
            SELECT r.id, p.code FROM roles r CROSS JOIN permissions p
            WHERE r.name = :role AND p.code IN ('appointment.read', 'appointment.create', 'appointment.manage')
        """).bindparams(role=role))
    op.execute("""
        CREATE TABLE patients (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE RESTRICT,
            patient_number text NOT NULL,
            full_name text NOT NULL,
            normalized_email text NULL,
            normalized_phone text NULL,
            date_of_birth date NULL,
            status text NOT NULL DEFAULT 'active',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz NULL,
            version integer NOT NULL DEFAULT 1,
            CONSTRAINT uq_patients_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT uq_patients_number UNIQUE (clinic_id, patient_number)
        )
    """)
    op.execute("""
        CREATE TABLE appointments (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            branch_id uuid NOT NULL,
            doctor_id uuid NULL,
            service_id uuid NOT NULL,
            patient_id uuid NOT NULL,
            starts_at timestamptz NOT NULL,
            ends_at timestamptz NOT NULL,
            occupancy_start timestamptz NOT NULL,
            occupancy_end timestamptz NOT NULL,
            occupancy tstzrange GENERATED ALWAYS AS (tstzrange(occupancy_start, occupancy_end, '[)')) STORED,
            status text NOT NULL DEFAULT 'requested',
            blocks_time boolean NOT NULL DEFAULT true,
            source text NOT NULL DEFAULT 'public',
            reference text NOT NULL,
            idempotency_key text NOT NULL,
            idempotency_body_hash char(64) NOT NULL,
            policy_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz NULL,
            version integer NOT NULL DEFAULT 1,
            CONSTRAINT uq_appointments_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT uq_appointments_reference UNIQUE (clinic_id, reference),
            CONSTRAINT uq_appointments_idempotency UNIQUE (clinic_id, idempotency_key),
            CONSTRAINT fk_appointments_branch_tenant FOREIGN KEY (clinic_id, branch_id) REFERENCES branches (clinic_id, id) ON DELETE RESTRICT,
            CONSTRAINT fk_appointments_doctor_tenant FOREIGN KEY (clinic_id, doctor_id) REFERENCES doctor_profiles (clinic_id, id) ON DELETE RESTRICT,
            CONSTRAINT fk_appointments_service_tenant FOREIGN KEY (clinic_id, service_id) REFERENCES services (clinic_id, id) ON DELETE RESTRICT,
            CONSTRAINT fk_appointments_patient_tenant FOREIGN KEY (clinic_id, patient_id) REFERENCES patients (clinic_id, id) ON DELETE RESTRICT,
            CONSTRAINT ck_appointments_time_order CHECK (starts_at < ends_at AND occupancy_start < occupancy_end)
        )
    """)
    op.execute("""
        ALTER TABLE appointments ADD CONSTRAINT no_doctor_overlap
        EXCLUDE USING gist (clinic_id WITH =, doctor_id WITH =, occupancy WITH &&)
        WHERE (blocks_time = true AND doctor_id IS NOT NULL)
    """)
    op.execute("""
        CREATE TABLE appointment_history (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            appointment_id uuid NOT NULL,
            from_status text NULL,
            to_status text NOT NULL,
            actor_user_id uuid NULL,
            reason text NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT fk_appointment_history_appointment_tenant FOREIGN KEY (clinic_id, appointment_id) REFERENCES appointments (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE booking_management_tokens (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            appointment_id uuid NOT NULL,
            secret_hash char(64) NOT NULL UNIQUE,
            expires_at timestamptz NOT NULL,
            revoked_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT fk_booking_tokens_appointment_tenant FOREIGN KEY (clinic_id, appointment_id) REFERENCES appointments (clinic_id, id) ON DELETE CASCADE
        )
    """)
    for table in ("patients", "appointments", "appointment_history", "booking_management_tokens"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(sa.text(f"""
            CREATE POLICY {table}_tenant_policy ON {table}
            USING (clinic_id = current_setting('app.clinic_id', true)::uuid)
            WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)
        """))
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON patients, appointments, appointment_history, booking_management_tokens TO healthcare_runtime")


def downgrade() -> None:
    for table in ("booking_management_tokens", "appointment_history", "appointments", "patients"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
