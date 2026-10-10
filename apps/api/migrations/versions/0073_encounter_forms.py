"""Create encounter forms for clinical visit documentation."""
from alembic import op
import sqlalchemy as sa

revision = "0073_encounter_forms"
down_revision = "0072_doctor_extended_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE encounter_forms (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            patient_id uuid NOT NULL,
            appointment_id uuid NULL,
            doctor_id uuid NOT NULL,
            branch_id uuid NULL,
            encounter_type text NOT NULL DEFAULT 'general',
            status text NOT NULL DEFAULT 'draft',
            chief_complaint text NULL,
            history_present_illness text NULL,
            examination_findings text NULL,
            diagnosis text NULL,
            investigations text NULL,
            treatment_plan text NULL,
            medications jsonb NULL DEFAULT '[]',
            procedures_performed text NULL,
            follow_up_instructions text NULL,
            follow_up_date date NULL,
            arrival_vitals jsonb NULL,
            discharge_vitals jsonb NULL,
            discharge_notes text NULL,
            internal_notes text NULL,
            created_by uuid NOT NULL,
            finalized_at timestamptz NULL,
            finalized_by uuid NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz NULL,
            version integer NOT NULL DEFAULT 1,
            CONSTRAINT uq_encounter_forms_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_encounter_type CHECK (encounter_type IN ('general', 'emergency', 'dental', 'dermatology', 'hair', 'skin', 'follow_up', 'procedure')),
            CONSTRAINT ck_encounter_status CHECK (status IN ('draft', 'in_review', 'finalized')),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES patients (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, doctor_id) REFERENCES doctor_profiles (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, appointment_id) REFERENCES appointments (clinic_id, id) ON DELETE SET NULL (appointment_id),
            FOREIGN KEY (clinic_id, branch_id) REFERENCES branches (clinic_id, id) ON DELETE SET NULL (branch_id)
        )
    """)
    op.execute("CREATE INDEX ix_encounter_forms_patient ON encounter_forms (clinic_id, patient_id, archived_at, created_at DESC)")
    op.execute("CREATE INDEX ix_encounter_forms_doctor ON encounter_forms (clinic_id, doctor_id, archived_at, created_at DESC)")
    op.execute("ALTER TABLE encounter_forms ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE encounter_forms FORCE ROW LEVEL SECURITY")
    op.execute(sa.text("CREATE POLICY encounter_forms_tenant_policy ON encounter_forms USING (clinic_id = current_setting('app.clinic_id', true)::uuid) WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)"))
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON encounter_forms TO healthcare_runtime")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS encounter_forms")
