"""Add token_number to appointments for booking-time token generation."""
from alembic import op

revision = "0090_appointment_token_number"
down_revision = "0089_staff_invitation_intended_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE appointments ADD COLUMN token_number integer NULL")
    op.execute("""
        CREATE TABLE appointment_token_sequences (
            clinic_id uuid NOT NULL,
            branch_id uuid NOT NULL,
            sequence_date date NOT NULL,
            next_value integer NOT NULL DEFAULT 1,
            PRIMARY KEY (clinic_id, branch_id, sequence_date),
            CONSTRAINT ck_token_seq_value CHECK (next_value > 0),
            FOREIGN KEY (clinic_id) REFERENCES clinics (id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, branch_id) REFERENCES branches (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("ALTER TABLE appointment_token_sequences ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE appointment_token_sequences FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY appointment_token_sequences_tenant_policy ON appointment_token_sequences "
        "USING (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid) "
        "WITH CHECK (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid)"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON appointment_token_sequences TO healthcare_runtime")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS appointment_token_sequences")
    op.execute("ALTER TABLE appointments DROP COLUMN IF EXISTS token_number")
