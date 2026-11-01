"""Add intended_role column and allow platform-initiated invitations."""
from alembic import op

revision = "0089_staff_invitation_intended_role"
down_revision = "0088_crm_performance_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE staff_invitations
        ADD COLUMN intended_role text NOT NULL DEFAULT 'receptionist'
    """)
    # Allow invited_by to be NULL for platform-admin-created clinic onboarding
    # invitations where the admin belongs to a different clinic.
    op.execute("ALTER TABLE staff_invitations ALTER COLUMN invited_by DROP NOT NULL")


def downgrade() -> None:
    op.execute("UPDATE staff_invitations SET invited_by = (SELECT id FROM users WHERE is_platform_admin = true LIMIT 1) WHERE invited_by IS NULL")
    op.execute("ALTER TABLE staff_invitations ALTER COLUMN invited_by SET NOT NULL")
    op.execute("ALTER TABLE staff_invitations DROP COLUMN intended_role")
