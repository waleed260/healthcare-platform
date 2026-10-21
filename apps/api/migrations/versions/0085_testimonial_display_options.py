"""add display_name and show_rating to website_testimonials

Revision ID: 0085_testimonial_display_options
Revises: 0084_add_canonical_url_to_posts
"""

revision = "0085_testimonial_display_options"
down_revision = "0084_add_canonical_url_to_posts"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("ALTER TABLE website_testimonials ADD COLUMN IF NOT EXISTS display_name text NOT NULL DEFAULT 'full' CHECK (display_name IN ('full', 'initials', 'anonymous'))")
    op.execute("ALTER TABLE website_testimonials ADD COLUMN IF NOT EXISTS show_rating boolean NOT NULL DEFAULT true")


def downgrade() -> None:
    op.execute("ALTER TABLE website_testimonials DROP COLUMN IF EXISTS show_rating")
    op.execute("ALTER TABLE website_testimonials DROP COLUMN IF EXISTS display_name")
