"""Add transactional per-clinic feature usage counters."""
from alembic import op


revision = "0018_feature_usage"
down_revision = "0017_permission_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE clinic_feature_usage (
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            feature_code text NOT NULL,
            period_start date NOT NULL,
            usage_count bigint NOT NULL DEFAULT 0 CHECK (usage_count >= 0),
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (clinic_id, feature_code, period_start)
        )
    """)
    op.execute("ALTER TABLE clinic_feature_usage ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE clinic_feature_usage FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY clinic_feature_usage_tenant_policy ON clinic_feature_usage
        USING (clinic_id = current_setting('app.clinic_id', true)::uuid)
        WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)
    """)
    op.execute("GRANT SELECT, INSERT, UPDATE ON clinic_feature_usage TO healthcare_runtime")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS clinic_feature_usage")
