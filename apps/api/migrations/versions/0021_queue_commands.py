"""Add optimistic locking and state constraints for queue commands."""
from alembic import op
import sqlalchemy as sa


revision = "0021_queue_commands"
down_revision = "0020_public_rate_limits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("queue_entries", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.create_check_constraint(
        "ck_queue_entries_status",
        "queue_entries",
        "status IN ('waiting', 'in_consultation', 'completed', 'cancelled')",
    )
    op.create_index("ix_queue_entries_active_branch", "queue_entries", ["clinic_id", "status", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_queue_entries_active_branch", table_name="queue_entries")
    op.drop_constraint("ck_queue_entries_status", "queue_entries", type_="check")
    op.drop_column("queue_entries", "version")
