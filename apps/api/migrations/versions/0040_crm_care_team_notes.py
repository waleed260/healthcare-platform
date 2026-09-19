"""Add tenant-safe patient care teams and care-team note visibility.

Requirement IDs: CRM-008, CRM-009, RBAC-002, TEN-001, TEN-004.
"""
from alembic import op


revision = "0040_crm_care_team_notes"
down_revision = "0039_website_media_versioning"
branch_labels = None
depends_on = None


def _tenant_policy(table: str) -> None:
    # NULLIF keeps an unset transaction-local context fail-closed without an
    # invalid UUID cast, matching the hardened policies from migration 0037.
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY {table}_tenant_policy ON {table}
        USING (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid)
        WITH CHECK (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid)
    """)


def upgrade() -> None:
    op.execute("ALTER TABLE patient_notes DROP CONSTRAINT ck_patient_notes_visibility")
    op.execute("""
        ALTER TABLE patient_notes
        ADD CONSTRAINT ck_patient_notes_visibility
        CHECK (visibility IN ('clinic', 'care_team', 'private_doctor'))
    """)

    op.execute("""
        CREATE TABLE clinic_care_policies (
            clinic_id uuid PRIMARY KEY REFERENCES clinics(id) ON DELETE CASCADE,
            allow_manager_care_team_notes boolean NOT NULL DEFAULT false,
            version integer NOT NULL DEFAULT 1,
            updated_by_user_id uuid NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT fk_clinic_care_policies_updated_by_tenant
                FOREIGN KEY (clinic_id, updated_by_user_id)
                REFERENCES users (clinic_id, id) ON DELETE SET NULL
        )
    """)
    op.execute("""
        CREATE TABLE patient_care_team (
            clinic_id uuid NOT NULL,
            patient_id uuid NOT NULL,
            doctor_id uuid NOT NULL,
            assigned_by_user_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (clinic_id, patient_id, doctor_id),
            FOREIGN KEY (clinic_id, patient_id)
                REFERENCES patients (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, doctor_id)
                REFERENCES doctor_profiles (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, assigned_by_user_id)
                REFERENCES users (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    _tenant_policy("clinic_care_policies")
    _tenant_policy("patient_care_team")
    op.execute("CREATE INDEX ix_patient_care_team_doctor ON patient_care_team (clinic_id, doctor_id, patient_id)")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON clinic_care_policies, patient_care_team TO healthcare_runtime")


def downgrade() -> None:
    # Do not silently weaken an existing care-team note during rollback.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM patient_notes WHERE visibility = 'care_team') THEN
                RAISE EXCEPTION 'cannot downgrade while care_team patient notes exist';
            END IF;
        END $$;
    """)
    op.execute("DROP INDEX IF EXISTS ix_patient_care_team_doctor")
    op.execute("DROP TABLE IF EXISTS patient_care_team")
    op.execute("DROP TABLE IF EXISTS clinic_care_policies")
    op.execute("ALTER TABLE patient_notes DROP CONSTRAINT ck_patient_notes_visibility")
    op.execute("""
        ALTER TABLE patient_notes
        ADD CONSTRAINT ck_patient_notes_visibility
        CHECK (visibility IN ('clinic', 'private_doctor'))
    """)
