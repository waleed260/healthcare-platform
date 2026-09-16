from alembic import op

revision = "0023_governance_integrity"
down_revision = "0022_holiday_scopes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE support_access_sessions ADD CONSTRAINT fk_support_requested_user FOREIGN KEY (clinic_id, requested_by_user_id) REFERENCES users (clinic_id, id) ON DELETE RESTRICT")
    op.execute("ALTER TABLE support_access_sessions ADD CONSTRAINT fk_support_approved_user FOREIGN KEY (clinic_id, approved_by_user_id) REFERENCES users (clinic_id, id) ON DELETE RESTRICT")
    op.execute("CREATE INDEX ix_support_access_clinic_expiry ON support_access_sessions (clinic_id, expires_at) WHERE revoked_at IS NULL")


def downgrade() -> None:
    op.drop_index("ix_support_access_clinic_expiry", table_name="support_access_sessions")
    op.execute("ALTER TABLE support_access_sessions DROP CONSTRAINT IF EXISTS fk_support_approved_user")
    op.execute("ALTER TABLE support_access_sessions DROP CONSTRAINT IF EXISTS fk_support_requested_user")
