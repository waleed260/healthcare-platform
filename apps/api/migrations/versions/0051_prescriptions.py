"""Add tenant-scoped prescription records to the shared clinical model."""
from alembic import op

revision = "0051_prescriptions"
down_revision = "0050_packages_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE prescriptions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            patient_id uuid NOT NULL,
            appointment_id uuid NULL,
            prescribed_by_user_id uuid NOT NULL,
            medication_name text NOT NULL,
            dosage text NULL,
            frequency text NULL,
            duration text NULL,
            instructions text NULL,
            status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed', 'discontinued')),
            version integer NOT NULL DEFAULT 1,
            prescribed_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_prescriptions_clinic_id UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES patients (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, appointment_id) REFERENCES appointments (clinic_id, id) ON DELETE SET NULL,
            FOREIGN KEY (clinic_id, prescribed_by_user_id) REFERENCES users (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    op.execute("ALTER TABLE prescriptions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE prescriptions FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY prescriptions_tenant_policy ON prescriptions USING (clinic_id = current_setting('app.clinic_id', true)::uuid) WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)""")
    op.execute("CREATE INDEX ix_prescriptions_patient ON prescriptions (clinic_id, patient_id, prescribed_at DESC)")
    op.execute("GRANT SELECT, INSERT, UPDATE ON prescriptions TO healthcare_runtime")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS prescriptions")
