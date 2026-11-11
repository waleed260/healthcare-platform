"""Add leads.branch_id for strict branch-scope enforcement.

Pre-booking leads previously had no branch anchor, which forced the scope
filter to either hide them from every branch-scoped user (original gap)
or show them to every one (temporary relaxation). This column lets a
lead be branch-assigned at any point in the pipeline; the route layer
treats a NULL value as "unassigned", visible only to users without
branch scopes (admins / central triage).

The column is nullable so existing rows migrate without backfill; the
route's scope SQL falls back to the linked appointment's branch when
``leads.branch_id`` is NULL.
"""
from alembic import op


revision = "0093_leads_branch_id"
down_revision = "0092_fix_rls_nullif_missed_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE leads ADD COLUMN branch_id uuid NULL")
    op.execute("""
        ALTER TABLE leads ADD CONSTRAINT fk_leads_branch
        FOREIGN KEY (clinic_id, branch_id) REFERENCES branches (clinic_id, id)
        ON DELETE SET NULL
    """)
    op.execute(
        "CREATE INDEX ix_leads_clinic_branch ON leads (clinic_id, branch_id) "
        "WHERE branch_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_leads_clinic_branch")
    op.execute("ALTER TABLE leads DROP CONSTRAINT IF EXISTS fk_leads_branch")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS branch_id")
