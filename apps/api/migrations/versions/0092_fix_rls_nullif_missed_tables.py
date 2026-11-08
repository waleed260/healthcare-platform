"""Add NULLIF guard to three tenant policies missed by 0086.

Without the guard, casting '' to uuid raises whenever a platform-admin
session (empty app.clinic_id) touches service_materials, refunds, or
encounter_forms.
"""
from alembic import op


revision = "0092_fix_rls_nullif_missed_tables"
down_revision = "0091_patient_media_details"
branch_labels = None
depends_on = None


_TENANT_POLICIES = (
    ("service_materials", "service_materials_tenant_policy", "ALL"),
    ("refunds", "refunds_tenant_policy", "ALL"),
    ("encounter_forms", "encounter_forms_tenant_policy", "ALL"),
    ("patient_admissions", "patient_admissions_tenant", "ALL"),
    ("staff_invitations", "staff_invitations_update_policy", "UPDATE"),
)


def upgrade() -> None:
    for table, policy, cmd in _TENANT_POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        op.execute(
            f"CREATE POLICY {policy} ON {table} FOR {cmd} "
            "USING (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid) "
            "WITH CHECK (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid)"
        )
    # staff_invitations_read_policy allows anonymous lookup (empty clinic context) during
    # invitation redemption. The original OR-ordering put the cast first — PG evaluates the
    # cast before honouring the OR short-circuit, so an empty setting crashed before the
    # NULL/'' branches could rescue it. Reorder the branches.
    op.execute("DROP POLICY IF EXISTS staff_invitations_read_policy ON staff_invitations")
    op.execute(
        "CREATE POLICY staff_invitations_read_policy ON staff_invitations FOR SELECT "
        "USING ("
        "current_setting('app.clinic_id', true) IS NULL "
        "OR current_setting('app.clinic_id', true) = '' "
        "OR clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid"
        ")"
    )
    # Same crash risk for delete/insert policies on the same table.
    op.execute("DROP POLICY IF EXISTS staff_invitations_delete_policy ON staff_invitations")
    op.execute(
        "CREATE POLICY staff_invitations_delete_policy ON staff_invitations FOR DELETE "
        "USING (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid)"
    )
    op.execute("DROP POLICY IF EXISTS staff_invitations_write_policy ON staff_invitations")
    op.execute(
        "CREATE POLICY staff_invitations_write_policy ON staff_invitations FOR INSERT "
        "WITH CHECK (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS staff_invitations_write_policy ON staff_invitations")
    op.execute(
        "CREATE POLICY staff_invitations_write_policy ON staff_invitations FOR INSERT "
        "WITH CHECK (clinic_id = (current_setting('app.clinic_id', true))::uuid)"
    )
    op.execute("DROP POLICY IF EXISTS staff_invitations_delete_policy ON staff_invitations")
    op.execute(
        "CREATE POLICY staff_invitations_delete_policy ON staff_invitations FOR DELETE "
        "USING (clinic_id = (current_setting('app.clinic_id', true))::uuid)"
    )
    op.execute("DROP POLICY IF EXISTS staff_invitations_read_policy ON staff_invitations")
    op.execute(
        "CREATE POLICY staff_invitations_read_policy ON staff_invitations FOR SELECT "
        "USING ("
        "(clinic_id = (current_setting('app.clinic_id', true))::uuid) "
        "OR (current_setting('app.clinic_id', true) IS NULL) "
        "OR (current_setting('app.clinic_id', true) = '')"
        ")"
    )
    for table, policy, cmd in _TENANT_POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        op.execute(
            f"CREATE POLICY {policy} ON {table} FOR {cmd} "
            "USING (clinic_id = (current_setting('app.clinic_id', true))::uuid) "
            "WITH CHECK (clinic_id = (current_setting('app.clinic_id', true))::uuid)"
        )
