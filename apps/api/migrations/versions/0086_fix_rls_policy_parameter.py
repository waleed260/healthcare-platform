"""fix RLS policies using wrong app.current_tenant parameter

Revision ID: 0086_fix_rls_policy_parameter
Revises: 0085_testimonial_display_options
"""

revision = "0086_fix_rls_policy_parameter"
down_revision = "0085_testimonial_display_options"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("DROP POLICY IF EXISTS patient_vitals_tenant ON patient_vitals")
    op.execute(
        "CREATE POLICY patient_vitals_tenant ON patient_vitals "
        "USING (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid)"
    )

    op.execute("DROP POLICY IF EXISTS patient_transfers_tenant ON patient_transfers")
    op.execute(
        "CREATE POLICY patient_transfers_tenant ON patient_transfers "
        "USING (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid)"
    )

    op.execute("DROP POLICY IF EXISTS patient_discharges_tenant ON patient_discharges")
    op.execute(
        "CREATE POLICY patient_discharges_tenant ON patient_discharges "
        "USING (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid)"
    )

    op.execute("DROP POLICY IF EXISTS internal_tasks_tenant ON internal_tasks")
    op.execute(
        "CREATE POLICY internal_tasks_tenant ON internal_tasks "
        "USING (clinic_id = NULLIF(current_setting('app.clinic_id', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS patient_vitals_tenant ON patient_vitals")
    op.execute(
        "CREATE POLICY patient_vitals_tenant ON patient_vitals "
        "USING (clinic_id = current_setting('app.current_tenant')::uuid)"
    )

    op.execute("DROP POLICY IF EXISTS patient_transfers_tenant ON patient_transfers")
    op.execute(
        "CREATE POLICY patient_transfers_tenant ON patient_transfers "
        "USING (clinic_id = current_setting('app.current_tenant')::uuid)"
    )

    op.execute("DROP POLICY IF EXISTS patient_discharges_tenant ON patient_discharges")
    op.execute(
        "CREATE POLICY patient_discharges_tenant ON patient_discharges "
        "USING (clinic_id = current_setting('app.current_tenant')::uuid)"
    )

    op.execute("DROP POLICY IF EXISTS internal_tasks_tenant ON internal_tasks")
    op.execute(
        "CREATE POLICY internal_tasks_tenant ON internal_tasks "
        "USING (clinic_id = current_setting('app.current_tenant')::uuid)"
    )
