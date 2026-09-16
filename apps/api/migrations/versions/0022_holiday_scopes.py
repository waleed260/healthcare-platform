"""Support branch-specific and time-range clinic holiday closures."""
from alembic import op


revision = "0022_holiday_scopes"
down_revision = "0021_queue_commands"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE clinic_holidays ADD COLUMN branch_id uuid NULL")
    op.execute("ALTER TABLE clinic_holidays ADD COLUMN starts_at time NULL")
    op.execute("ALTER TABLE clinic_holidays ADD COLUMN ends_at time NULL")
    op.execute("ALTER TABLE clinic_holidays ADD CONSTRAINT fk_clinic_holidays_branch_tenant FOREIGN KEY (clinic_id, branch_id) REFERENCES branches (clinic_id, id) ON DELETE CASCADE")
    op.drop_constraint("uq_clinic_holidays_date", "clinic_holidays", type_="unique")
    op.execute("ALTER TABLE clinic_holidays ADD CONSTRAINT ck_clinic_holidays_interval CHECK ((starts_at IS NULL AND ends_at IS NULL) OR (starts_at IS NOT NULL AND ends_at IS NOT NULL AND starts_at < ends_at))")
    op.execute("""
        CREATE UNIQUE INDEX uq_clinic_holidays_scope
        ON clinic_holidays (
            clinic_id, holiday_date,
            COALESCE(branch_id, '00000000-0000-0000-0000-000000000000'::uuid),
            COALESCE(starts_at, '00:00:00'::time), COALESCE(ends_at, '00:00:00'::time)
        )
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_clinic_holidays_scope")
    op.drop_constraint("ck_clinic_holidays_interval", "clinic_holidays", type_="check")
    op.drop_constraint("fk_clinic_holidays_branch_tenant", "clinic_holidays", type_="foreignkey")
    op.drop_column("clinic_holidays", "ends_at")
    op.drop_column("clinic_holidays", "starts_at")
    op.drop_column("clinic_holidays", "branch_id")
    op.create_unique_constraint("uq_clinic_holidays_date", "clinic_holidays", ["clinic_id", "holiday_date"])
