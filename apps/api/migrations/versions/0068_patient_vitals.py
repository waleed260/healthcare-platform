"""Add patient_vitals table for BP, conditions, and procedures."""

revision = "0068_patient_vitals"
down_revision = "0067_invoice_void_refunds"

from alembic import op


def upgrade() -> None:
    op.execute("""
        CREATE TABLE patient_vitals (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            patient_id uuid NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT now(),
            vital_type text NOT NULL,
            label text NULL,
            value_text text NULL,
            value_systolic integer NULL,
            value_diastolic integer NULL,
            value_numeric numeric NULL,
            unit text NULL,
            notes text NULL,
            recorded_by uuid NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz NULL,
            version integer NOT NULL DEFAULT 1,
            CONSTRAINT uq_patient_vitals_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT fk_patient_vitals_patient FOREIGN KEY (clinic_id, patient_id) REFERENCES patients (clinic_id, id) ON DELETE RESTRICT,
            CONSTRAINT ck_patient_vitals_type CHECK (vital_type IN ('blood_pressure', 'condition', 'procedure', 'allergy', 'temperature', 'heart_rate', 'weight', 'height', 'note'))
        )
    """)
    op.execute("CREATE INDEX ix_patient_vitals_patient ON patient_vitals (clinic_id, patient_id, archived_at, recorded_at DESC)")
    op.execute("ALTER TABLE patient_vitals ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE patient_vitals FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY patient_vitals_tenant ON patient_vitals USING (clinic_id = current_setting('app.current_tenant')::uuid)")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON patient_vitals TO healthcare_runtime")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS patient_vitals")
