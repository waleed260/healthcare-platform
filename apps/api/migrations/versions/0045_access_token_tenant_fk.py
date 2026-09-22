"""Protect clinic-scoped access tokens with a same-tenant user relationship."""

from alembic import op


revision = "0045_access_token_tenant_fk"
down_revision = "0044_support_context_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A NULL clinic_id remains valid for platform-scoped tokens. When a token
    # is clinic-scoped, PostgreSQL now requires its user to belong to that
    # same clinic through the existing users (clinic_id, id) unique key.
    op.execute("ALTER TABLE access_tokens DROP CONSTRAINT access_tokens_user_id_fkey")
    op.execute("""
        ALTER TABLE access_tokens
        ADD CONSTRAINT fk_access_tokens_user_tenant
        FOREIGN KEY (clinic_id, user_id) REFERENCES users (clinic_id, id) ON DELETE CASCADE
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE access_tokens DROP CONSTRAINT fk_access_tokens_user_tenant")
    op.execute("""
        ALTER TABLE access_tokens
        ADD CONSTRAINT access_tokens_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    """)
