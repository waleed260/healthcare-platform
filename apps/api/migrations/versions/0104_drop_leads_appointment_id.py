"""Deferred cleanup: drop the legacy one-to-one leads.appointment_id scalar.

Safe now that the one-to-many link lives on appointments.lead_id (0099, backfilled) and every
reader has moved to it: the lead list/detail no longer select it and the branch-scope fallback
derives the branch from the lead's most-recent linked appointment via appointments.lead_id.
Dropping the column also drops its dependent composite FK. Reversible (re-adds column + FK).
"""
from alembic import op

revision = "0104_drop_leads_appointment_id"
down_revision = "0103_lead_follow_ups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS appointment_id")


def downgrade() -> None:
    op.execute("ALTER TABLE leads ADD COLUMN appointment_id uuid NULL")
    op.execute("""
        ALTER TABLE leads ADD CONSTRAINT leads_appointment_fk
        FOREIGN KEY (clinic_id, appointment_id) REFERENCES appointments (clinic_id, id) ON DELETE SET NULL
    """)
