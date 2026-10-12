"""Extend encounter_forms with arrival, clinical, administered treatment, discharge, and amendment fields."""
from alembic import op

revision = "0075_encounter_extensions"
down_revision = "0074_patient_admissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- A. Expand status constraint ---
    op.execute("ALTER TABLE encounter_forms DROP CONSTRAINT ck_encounter_status")
    op.execute("""
        ALTER TABLE encounter_forms ADD CONSTRAINT ck_encounter_status
        CHECK (status IN ('draft','in_progress','ready_for_discharge','discharged','finalized','referred','transferred'))
    """)
    op.execute("UPDATE encounter_forms SET status = 'in_progress' WHERE status = 'in_review'")

    # --- B. Add columns: Arrival ---
    op.execute("ALTER TABLE encounter_forms ADD COLUMN arrival_mode text NULL")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN arrival_datetime timestamptz NULL")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN attendant_name text NULL")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN attendant_phone text NULL")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN condition_on_arrival text NULL")

    # --- B. Add columns: Clinical/Assessment ---
    op.execute("ALTER TABLE encounter_forms ADD COLUMN known_allergies text NULL")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN allergy_status text NOT NULL DEFAULT 'unknown'")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN medical_history text NULL")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN current_medications_text text NULL")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN symptom_duration text NULL")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN gcs_eye integer NULL")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN gcs_verbal integer NULL")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN gcs_motor integer NULL")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN pain_score integer NULL")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN investigation_results text NULL")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN clinical_assessment text NULL")

    # --- B. Add columns: Administered treatments ---
    op.execute("ALTER TABLE encounter_forms ADD COLUMN administered_treatments jsonb NULL DEFAULT '[]'")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN administered_procedures jsonb NULL DEFAULT '[]'")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN treatment_response text NULL")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN adverse_reactions text NULL")

    # --- B. Add columns: Discharge extension ---
    op.execute("ALTER TABLE encounter_forms ADD COLUMN discharge_condition text NULL")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN discharge_outcome text NULL")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN discharge_destination text NULL")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN discharge_reason text NULL")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN discharge_datetime timestamptz NULL")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN discharged_by uuid NULL")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN discharge_instructions text NULL")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN warning_signs text NULL")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN medicine_guidance text NULL")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN follow_up_clinician text NULL")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN follow_up_department text NULL")
    op.execute("ALTER TABLE encounter_forms ADD COLUMN referral_instructions text NULL")

    # --- B. Add columns: Amendment history ---
    op.execute("ALTER TABLE encounter_forms ADD COLUMN amendment_history jsonb NULL DEFAULT '[]'")

    # --- B. Constraints ---
    op.execute("ALTER TABLE encounter_forms ADD CONSTRAINT ck_allergy_status CHECK (allergy_status IN ('unknown','none_known','has_allergies'))")
    op.execute("ALTER TABLE encounter_forms ADD CONSTRAINT ck_discharge_outcome CHECK (discharge_outcome IS NULL OR discharge_outcome IN ('home','referral','transfer','against_advice','admitted'))")
    op.execute("ALTER TABLE encounter_forms ADD CONSTRAINT ck_gcs_eye CHECK (gcs_eye IS NULL OR (gcs_eye >= 1 AND gcs_eye <= 4))")
    op.execute("ALTER TABLE encounter_forms ADD CONSTRAINT ck_gcs_verbal CHECK (gcs_verbal IS NULL OR (gcs_verbal >= 1 AND gcs_verbal <= 5))")
    op.execute("ALTER TABLE encounter_forms ADD CONSTRAINT ck_gcs_motor CHECK (gcs_motor IS NULL OR (gcs_motor >= 1 AND gcs_motor <= 6))")
    op.execute("ALTER TABLE encounter_forms ADD CONSTRAINT ck_pain_score CHECK (pain_score IS NULL OR (pain_score >= 0 AND pain_score <= 10))")

    # --- C. Link prescriptions to encounters ---
    op.execute("ALTER TABLE prescriptions ADD COLUMN encounter_id uuid NULL")
    op.execute("CREATE INDEX ix_prescriptions_encounter ON prescriptions (clinic_id, encounter_id) WHERE encounter_id IS NOT NULL")

    # Grant to runtime role
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON encounter_forms TO healthcare_runtime")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_prescriptions_encounter")
    op.execute("ALTER TABLE prescriptions DROP COLUMN IF EXISTS encounter_id")

    op.execute("ALTER TABLE encounter_forms DROP CONSTRAINT IF EXISTS ck_pain_score")
    op.execute("ALTER TABLE encounter_forms DROP CONSTRAINT IF EXISTS ck_gcs_motor")
    op.execute("ALTER TABLE encounter_forms DROP CONSTRAINT IF EXISTS ck_gcs_verbal")
    op.execute("ALTER TABLE encounter_forms DROP CONSTRAINT IF EXISTS ck_gcs_eye")
    op.execute("ALTER TABLE encounter_forms DROP CONSTRAINT IF EXISTS ck_discharge_outcome")
    op.execute("ALTER TABLE encounter_forms DROP CONSTRAINT IF EXISTS ck_allergy_status")

    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS amendment_history")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS referral_instructions")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS follow_up_department")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS follow_up_clinician")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS medicine_guidance")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS warning_signs")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS discharge_instructions")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS discharged_by")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS discharge_datetime")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS discharge_reason")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS discharge_destination")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS discharge_outcome")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS discharge_condition")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS adverse_reactions")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS treatment_response")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS administered_procedures")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS administered_treatments")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS clinical_assessment")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS investigation_results")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS pain_score")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS gcs_motor")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS gcs_verbal")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS gcs_eye")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS symptom_duration")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS current_medications_text")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS medical_history")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS allergy_status")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS known_allergies")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS condition_on_arrival")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS attendant_phone")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS attendant_name")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS arrival_datetime")
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS arrival_mode")

    op.execute("UPDATE encounter_forms SET status = 'in_review' WHERE status = 'in_progress'")
    op.execute("ALTER TABLE encounter_forms DROP CONSTRAINT ck_encounter_status")
    op.execute("ALTER TABLE encounter_forms ADD CONSTRAINT ck_encounter_status CHECK (status IN ('draft','in_review','finalized'))")
