"""Allow invitation consumption without pre-existing tenant context.

staff_invitations had a single tenant-scoped RLS policy, which blocked the
SELECT-by-token lookup needed during invitation consumption (the clinic_id is
not yet known at that point).  Split the policy: SELECT is permitted without
tenant context so the token lookup succeeds; writes still require context.
"""
from alembic import op

revision = "0077_invitation_rls_allow_consume"
down_revision = "0076_encounter_token_number"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP POLICY IF EXISTS staff_invitations_tenant_policy ON staff_invitations")
    op.execute("""
        CREATE POLICY staff_invitations_read_policy ON staff_invitations
        FOR SELECT
        USING (
            clinic_id = current_setting('app.clinic_id', true)::uuid
            OR current_setting('app.clinic_id', true) IS NULL
            OR current_setting('app.clinic_id', true) = ''
        )
    """)
    op.execute("""
        CREATE POLICY staff_invitations_write_policy ON staff_invitations
        FOR INSERT
        WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)
    """)
    op.execute("""
        CREATE POLICY staff_invitations_update_policy ON staff_invitations
        FOR UPDATE
        USING (clinic_id = current_setting('app.clinic_id', true)::uuid)
        WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)
    """)
    op.execute("""
        CREATE POLICY staff_invitations_delete_policy ON staff_invitations
        FOR DELETE
        USING (clinic_id = current_setting('app.clinic_id', true)::uuid)
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS staff_invitations_delete_policy ON staff_invitations")
    op.execute("DROP POLICY IF EXISTS staff_invitations_update_policy ON staff_invitations")
    op.execute("DROP POLICY IF EXISTS staff_invitations_write_policy ON staff_invitations")
    op.execute("DROP POLICY IF EXISTS staff_invitations_read_policy ON staff_invitations")
    op.execute("""
        CREATE POLICY staff_invitations_tenant_policy ON staff_invitations
        USING (clinic_id = current_setting('app.clinic_id', true)::uuid)
        WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)
    """)
