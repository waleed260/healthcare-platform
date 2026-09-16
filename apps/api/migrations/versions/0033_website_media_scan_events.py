"""Persist immutable scan decisions for website media."""
from alembic import op


revision = "0033_website_media_scan_events"
down_revision = "0032_website_public_assets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE website_media_scan_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            media_id uuid NOT NULL,
            engine text NOT NULL,
            signature_version text NOT NULL,
            outcome text NOT NULL,
            failure_reason text NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_website_media_scan_events_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_website_media_scan_outcome CHECK (outcome IN ('clean', 'quarantined', 'scan_failed')),
            FOREIGN KEY (clinic_id, media_id) REFERENCES website_media (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("ALTER TABLE website_media_scan_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE website_media_scan_events FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY website_media_scan_events_tenant_policy ON website_media_scan_events USING (clinic_id = current_setting('app.clinic_id', true)::uuid) WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)")
    op.execute("CREATE INDEX ix_website_media_scan_events_media ON website_media_scan_events (clinic_id, media_id, created_at DESC)")
    op.execute("GRANT SELECT, INSERT ON website_media_scan_events TO healthcare_runtime")


def downgrade() -> None:
    op.drop_index("ix_website_media_scan_events_media", table_name="website_media_scan_events")
    op.execute("DROP TABLE IF EXISTS website_media_scan_events")
