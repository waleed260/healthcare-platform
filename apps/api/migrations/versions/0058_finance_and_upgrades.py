"""Add clinic expenses, upgrade requests, and plan pricing for platform reporting."""
from alembic import op
import sqlalchemy as sa

revision = "0058_finance_and_upgrades"
down_revision = "0057_lead_activities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for code, description in (("expense.read", "Read clinic expenses and cashier summaries"), ("expense.manage", "Record and void clinic expenses")):
        op.execute(sa.text("INSERT INTO permissions (code, description) VALUES (:code, :description) ON CONFLICT (code) DO NOTHING").bindparams(code=code, description=description))
    for role, codes in {"owner": ("expense.read", "expense.manage"), "manager": ("expense.read", "expense.manage"), "accountant": ("expense.read", "expense.manage")}.items():
        for code in codes:
            op.execute(sa.text("INSERT INTO role_permissions (role_id, permission_code) SELECT r.id, :code FROM roles r WHERE r.name = :role ON CONFLICT DO NOTHING").bindparams(role=role, code=code))
    op.execute("""
        CREATE TABLE expenses (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            branch_id uuid NULL,
            category text NOT NULL,
            description text NOT NULL,
            amount_minor bigint NOT NULL CHECK (amount_minor > 0),
            currency char(3) NOT NULL,
            incurred_on date NOT NULL,
            recorded_by_user_id uuid NOT NULL,
            voided_at timestamptz NULL,
            void_reason text NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_expenses_clinic_id UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, branch_id) REFERENCES branches (clinic_id, id) ON DELETE SET NULL (branch_id),
            FOREIGN KEY (clinic_id, recorded_by_user_id) REFERENCES users (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    op.execute("CREATE INDEX ix_expenses_clinic_day ON expenses (clinic_id, incurred_on DESC)")
    op.execute("""
        CREATE TABLE upgrade_requests (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            requested_by_user_id uuid NOT NULL,
            kind text NOT NULL CHECK (kind IN ('specialty', 'feature', 'limit')),
            target_code text NOT NULL,
            message text NULL,
            status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'declined', 'cancelled')),
            decided_by_user_id uuid NULL,
            decision_note text NULL,
            decided_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_upgrade_requests_clinic_id UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, requested_by_user_id) REFERENCES users (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    op.execute("CREATE UNIQUE INDEX uq_upgrade_requests_open ON upgrade_requests (clinic_id, kind, target_code) WHERE status = 'pending'")
    op.execute("CREATE INDEX ix_upgrade_requests_status ON upgrade_requests (status, created_at DESC)")
    for table in ("expenses", "upgrade_requests"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY expenses_tenant_policy ON expenses USING (clinic_id = current_setting('app.clinic_id', true)::uuid) WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)")
    op.execute("""
        CREATE POLICY upgrade_requests_tenant_policy ON upgrade_requests
        USING (clinic_id = current_setting('app.clinic_id', true)::uuid OR current_setting('app.is_platform_admin', true) = 'true')
        WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid OR current_setting('app.is_platform_admin', true) = 'true')
    """)
    op.execute("ALTER TABLE plans ADD COLUMN monthly_price_minor bigint NOT NULL DEFAULT 0 CHECK (monthly_price_minor >= 0)")
    op.execute("ALTER TABLE plans ADD COLUMN currency char(3) NOT NULL DEFAULT 'PKR'")
    op.execute("ALTER TABLE clinic_subscriptions ADD COLUMN renewal_at timestamptz NULL")
    op.execute("CREATE POLICY clinic_subscriptions_platform_read ON clinic_subscriptions FOR SELECT USING (current_setting('app.is_platform_admin', true) = 'true')")
    op.execute("GRANT SELECT, INSERT, UPDATE ON expenses, upgrade_requests TO healthcare_runtime")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS clinic_subscriptions_platform_read ON clinic_subscriptions")
    op.execute("ALTER TABLE clinic_subscriptions DROP COLUMN IF EXISTS renewal_at")
    op.execute("ALTER TABLE plans DROP COLUMN IF EXISTS currency")
    op.execute("ALTER TABLE plans DROP COLUMN IF EXISTS monthly_price_minor")
    op.execute("DROP TABLE IF EXISTS upgrade_requests")
    op.execute("DROP TABLE IF EXISTS expenses")
