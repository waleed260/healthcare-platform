"""Repair the theme_instances tenant policy's empty-clinic UUID cast.

Migrations 0037 and 0065 contain broad tenant-policy hardening passes, but the
restored production snapshot at revision 0094 was reported to retain the
original unguarded expression. Repository history alone does not establish
why that snapshot diverged.

Use ALTER POLICY rather than DROP/CREATE so the existing policy's roles,
command scope, and permissive mode remain unchanged.
"""
from alembic import op


revision = "0105_fix_theme_instances_nullif"
down_revision = "0104_drop_leads_appointment_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER POLICY theme_instances_tenant_policy ON theme_instances
        USING (
            clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid
        )
        WITH CHECK (
            clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid
        )
        """
    )


def downgrade() -> None:
    """Restore the pre-fix expression (which reintroduces the empty-string cast risk)."""
    op.execute(
        """
        ALTER POLICY theme_instances_tenant_policy ON theme_instances
        USING (clinic_id = current_setting('app.clinic_id', true)::uuid)
        WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)
        """
    )
