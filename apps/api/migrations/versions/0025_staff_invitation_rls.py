"""Harden clinic-owned staff invitations with tenant RLS and composite identity FK."""
from alembic import op

revision = "0025_staff_invitation_rls"
down_revision = "0024_privacy_exports_retention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE staff_invitations ADD CONSTRAINT fk_staff_invited_by_tenant FOREIGN KEY (clinic_id, invited_by) REFERENCES users (clinic_id, id) ON DELETE RESTRICT")
    op.execute("ALTER TABLE staff_invitations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE staff_invitations FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY staff_invitations_tenant_policy ON staff_invitations USING (clinic_id = current_setting('app.clinic_id', true)::uuid) WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)")
    op.execute("CREATE INDEX ix_staff_invitations_clinic_state ON staff_invitations (clinic_id, expires_at, consumed_at, revoked_at)")


def downgrade() -> None:
    op.drop_index("ix_staff_invitations_clinic_state", table_name="staff_invitations")
    op.execute("DROP POLICY IF EXISTS staff_invitations_tenant_policy ON staff_invitations")
    op.execute("ALTER TABLE staff_invitations DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE staff_invitations DROP CONSTRAINT IF EXISTS fk_staff_invited_by_tenant")
