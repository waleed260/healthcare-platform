"""Add short-lived hashed tokens for draft website previews."""
from alembic import op

revision = "0027_website_preview_tokens"
down_revision = "0026_booking_questions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE website_preview_tokens (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(), clinic_id uuid NOT NULL, website_id uuid NOT NULL,
            token_hash char(64) NOT NULL UNIQUE, expires_at timestamptz NOT NULL, revoked_at timestamptz NULL,
            created_by uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_website_preview_tokens_clinic_id UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, website_id) REFERENCES websites (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, created_by) REFERENCES users (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    op.execute("ALTER TABLE website_preview_tokens ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE website_preview_tokens FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY website_preview_tokens_tenant_policy ON website_preview_tokens USING (clinic_id = current_setting('app.clinic_id', true)::uuid) WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)")
    op.execute("CREATE INDEX ix_website_preview_tokens_active ON website_preview_tokens (clinic_id, website_id, expires_at) WHERE revoked_at IS NULL")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON website_preview_tokens TO healthcare_runtime")


def downgrade() -> None:
    op.drop_index("ix_website_preview_tokens_active", table_name="website_preview_tokens")
    op.execute("DROP TABLE IF EXISTS website_preview_tokens")
