"""Add database-backed fixed-window rate-limit buckets for public endpoints."""
from alembic import op


revision = "0020_public_rate_limits"
down_revision = "0019_document_access_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE public_rate_limit_buckets (
            bucket_key char(64) PRIMARY KEY,
            window_started_at timestamptz NOT NULL DEFAULT now(),
            request_count integer NOT NULL DEFAULT 0 CHECK (request_count >= 0),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON public_rate_limit_buckets TO healthcare_runtime")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public_rate_limit_buckets")
