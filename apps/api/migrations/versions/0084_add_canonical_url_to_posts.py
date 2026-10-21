"""add canonical_url to website_posts

Revision ID: 0084_add_canonical_url_to_posts
Revises: 0083_grant_inventory_permissions_to_all_roles
"""

revision = "0084_add_canonical_url_to_posts"
down_revision = "0083_grant_inventory_permissions_to_all_roles"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("ALTER TABLE website_posts ADD COLUMN IF NOT EXISTS canonical_url text")


def downgrade() -> None:
    op.execute("ALTER TABLE website_posts DROP COLUMN IF EXISTS canonical_url")
