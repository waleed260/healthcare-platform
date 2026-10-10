"""Add emergency_contact, preferred_communication, contraindications to patients."""

revision = "0070_patient_extended_fields"
down_revision = "0069_patient_transfers_discharges"

from alembic import op


def upgrade() -> None:
    op.execute("""
        ALTER TABLE patients
        ADD COLUMN IF NOT EXISTS emergency_contact_name text NULL,
        ADD COLUMN IF NOT EXISTS emergency_contact_phone text NULL,
        ADD COLUMN IF NOT EXISTS emergency_contact_relation text NULL,
        ADD COLUMN IF NOT EXISTS preferred_communication text NULL DEFAULT 'phone',
        ADD COLUMN IF NOT EXISTS contraindications text NULL,
        ADD COLUMN IF NOT EXISTS allergies_summary text NULL
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE patients
        DROP COLUMN IF EXISTS emergency_contact_name,
        DROP COLUMN IF EXISTS emergency_contact_phone,
        DROP COLUMN IF EXISTS emergency_contact_relation,
        DROP COLUMN IF EXISTS preferred_communication,
        DROP COLUMN IF EXISTS contraindications,
        DROP COLUMN IF EXISTS allergies_summary
    """)
