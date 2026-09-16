"""Add an explicit platform-admin context for global administration APIs."""
from alembic import op
import sqlalchemy as sa


revision = "0036_platform_admin_context"
down_revision = "0035_inventory_and_hours"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_platform_admin", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("DROP POLICY audit_events_tenant_policy ON audit_events")
    op.execute("""
        CREATE POLICY audit_events_tenant_policy ON audit_events
        USING (
            clinic_id = current_setting('app.clinic_id', true)::uuid
            OR (clinic_id IS NULL AND current_setting('app.is_platform_admin', true) = 'true')
        )
        WITH CHECK (
            clinic_id = current_setting('app.clinic_id', true)::uuid
            OR (clinic_id IS NULL AND current_setting('app.is_platform_admin', true) = 'true')
        )
    """)


def downgrade() -> None:
    op.execute("DROP POLICY audit_events_tenant_policy ON audit_events")
    op.execute("CREATE POLICY audit_events_tenant_policy ON audit_events USING (clinic_id = current_setting('app.clinic_id', true)::uuid) WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)")
    op.drop_column("users", "is_platform_admin")
