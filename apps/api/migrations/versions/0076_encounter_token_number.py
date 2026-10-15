"""Add token_number to encounter_forms for daily sequential numbering."""
from alembic import op

revision = "0076_encounter_token_number"
down_revision = "0075_encounter_extensions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE encounter_forms ADD COLUMN token_number integer NULL")
    op.execute("""
        WITH numbered AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY clinic_id, DATE(created_at AT TIME ZONE 'UTC')
                       ORDER BY created_at
                   ) AS rn
            FROM encounter_forms
        )
        UPDATE encounter_forms SET token_number = numbered.rn
        FROM numbered WHERE encounter_forms.id = numbered.id
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE encounter_forms DROP COLUMN IF EXISTS token_number")
