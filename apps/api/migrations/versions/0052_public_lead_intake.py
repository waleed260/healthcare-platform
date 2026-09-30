"""Add idempotency keys for public website lead intake."""
from alembic import op
import sqlalchemy as sa

revision = "0052_public_lead_intake"
down_revision = "0051_prescriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("intake_key", sa.String(length=128), nullable=True))
    op.execute("CREATE UNIQUE INDEX uq_leads_public_intake_key ON leads (clinic_id, intake_key) WHERE intake_key IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_leads_public_intake_key")
    op.drop_column("leads", "intake_key")
