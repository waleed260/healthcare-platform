"""Add patient_transfers and patient_discharges tables."""

revision = "0069_patient_transfers_discharges"
down_revision = "0068_patient_vitals"

from alembic import op


def upgrade() -> None:
    op.execute("""
        CREATE TABLE patient_transfers (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            patient_id uuid NOT NULL,
            from_branch_id uuid NOT NULL,
            to_branch_id uuid NOT NULL,
            from_doctor_id uuid NULL,
            to_doctor_id uuid NULL,
            reason text NOT NULL,
            notes text NULL,
            status text NOT NULL DEFAULT 'pending',
            transferred_at timestamptz NULL,
            requested_by uuid NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz NULL,
            version integer NOT NULL DEFAULT 1,
            CONSTRAINT uq_patient_transfers_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT fk_patient_transfers_patient FOREIGN KEY (clinic_id, patient_id) REFERENCES patients (clinic_id, id) ON DELETE RESTRICT,
            CONSTRAINT ck_patient_transfers_status CHECK (status IN ('pending', 'approved', 'completed', 'rejected'))
        )
    """)
    op.execute("CREATE INDEX ix_patient_transfers_patient ON patient_transfers (clinic_id, patient_id, archived_at, created_at DESC)")
    op.execute("ALTER TABLE patient_transfers ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE patient_transfers FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY patient_transfers_tenant ON patient_transfers USING (clinic_id = current_setting('app.current_tenant')::uuid)")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON patient_transfers TO healthcare_runtime")

    op.execute("""
        CREATE TABLE patient_discharges (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            patient_id uuid NOT NULL,
            branch_id uuid NOT NULL,
            discharge_type text NOT NULL DEFAULT 'regular',
            diagnosis text NULL,
            treatment_summary text NULL,
            discharge_instructions text NULL,
            follow_up_required boolean NOT NULL DEFAULT false,
            follow_up_date date NULL,
            discharged_by uuid NULL,
            discharged_at timestamptz NOT NULL DEFAULT now(),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz NULL,
            version integer NOT NULL DEFAULT 1,
            CONSTRAINT uq_patient_discharges_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT fk_patient_discharges_patient FOREIGN KEY (clinic_id, patient_id) REFERENCES patients (clinic_id, id) ON DELETE RESTRICT,
            CONSTRAINT ck_patient_discharges_type CHECK (discharge_type IN ('regular', 'against_advice', 'referral', 'transfer'))
        )
    """)
    op.execute("CREATE INDEX ix_patient_discharges_patient ON patient_discharges (clinic_id, patient_id, archived_at, discharged_at DESC)")
    op.execute("ALTER TABLE patient_discharges ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE patient_discharges FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY patient_discharges_tenant ON patient_discharges USING (clinic_id = current_setting('app.current_tenant')::uuid)")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON patient_discharges TO healthcare_runtime")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS patient_discharges")
    op.execute("DROP TABLE IF EXISTS patient_transfers")
