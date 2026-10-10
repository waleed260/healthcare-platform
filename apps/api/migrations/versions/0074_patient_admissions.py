"""Add patient_admissions table for inpatient episodes."""
from alembic import op
import sqlalchemy as sa

revision = "0074_patient_admissions"
down_revision = "0073_encounter_forms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE patient_admissions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            patient_id uuid NOT NULL,
            branch_id uuid NOT NULL,
            admitting_doctor_id uuid NOT NULL,
            consulting_doctor_id uuid NULL,
            ward text NULL,
            bed text NULL,
            admission_type text NOT NULL DEFAULT 'elective',
            reason text NOT NULL,
            diagnosis_on_admission text NULL,
            expected_stay_days integer NULL,
            status text NOT NULL DEFAULT 'admitted',
            admitted_at timestamptz NOT NULL DEFAULT now(),
            discharged_at timestamptz NULL,
            discharge_id uuid NULL,
            notes text NULL,
            created_by uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz NULL,
            version integer NOT NULL DEFAULT 1,
            CONSTRAINT uq_patient_admissions_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_admission_type CHECK (admission_type IN ('elective', 'emergency', 'transfer', 'observation')),
            CONSTRAINT ck_admission_status CHECK (status IN ('admitted', 'discharged', 'transferred', 'cancelled')),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES patients (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, branch_id) REFERENCES branches (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, admitting_doctor_id) REFERENCES doctor_profiles (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, consulting_doctor_id) REFERENCES doctor_profiles (clinic_id, id) ON DELETE SET NULL (consulting_doctor_id)
        )
    """)
    op.execute("CREATE INDEX ix_patient_admissions_patient ON patient_admissions (clinic_id, patient_id, archived_at, status)")
    op.execute("CREATE INDEX ix_patient_admissions_branch ON patient_admissions (clinic_id, branch_id, archived_at, status)")
    op.execute("ALTER TABLE patient_admissions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE patient_admissions FORCE ROW LEVEL SECURITY")
    op.execute(sa.text("CREATE POLICY patient_admissions_tenant ON patient_admissions USING (clinic_id = current_setting('app.clinic_id', true)::uuid) WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)"))
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON patient_admissions TO healthcare_runtime")

    op.execute("ALTER TABLE patient_transfers ADD COLUMN IF NOT EXISTS clinical_handover jsonb NULL")
    op.execute("ALTER TABLE patient_transfers ADD COLUMN IF NOT EXISTS admission_id uuid NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE patient_transfers DROP COLUMN IF EXISTS admission_id")
    op.execute("ALTER TABLE patient_transfers DROP COLUMN IF EXISTS clinical_handover")
    op.execute("DROP TABLE IF EXISTS patient_admissions")
