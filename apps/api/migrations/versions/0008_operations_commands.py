"""Add optimistic versioning and integrity checks for operations commands."""
from alembic import op
import sqlalchemy as sa

revision = "0008_operations_commands"
down_revision = "0007_operations_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("follow_up_tasks", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.create_index("ix_follow_up_tasks_due_status", "follow_up_tasks", ["clinic_id", "status", "due_at"])
    op.create_check_constraint(
        "ck_follow_up_tasks_status",
        "follow_up_tasks",
        "status IN ('due', 'contacted', 'booked', 'completed', 'closed')",
    )
    op.create_check_constraint(
        "ck_follow_up_tasks_priority",
        "follow_up_tasks",
        "priority IN ('low', 'normal', 'high')",
    )
    op.create_index("ix_notifications_user_unread", "notifications", ["clinic_id", "user_id", "read_at", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_notifications_user_unread", table_name="notifications")
    op.drop_constraint("ck_follow_up_tasks_priority", "follow_up_tasks", type_="check")
    op.drop_constraint("ck_follow_up_tasks_status", "follow_up_tasks", type_="check")
    op.drop_index("ix_follow_up_tasks_due_status", table_name="follow_up_tasks")
    op.drop_column("follow_up_tasks", "version")
