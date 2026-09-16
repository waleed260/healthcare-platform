"""Track immutable public keys for website assets promoted at publish time."""
from alembic import op
import sqlalchemy as sa


revision = "0032_website_public_assets"
down_revision = "0031_website_media_uploads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("website_media", sa.Column("public_storage_key", sa.Text(), nullable=True))
    op.create_unique_constraint("uq_website_media_public_storage_key", "website_media", ["public_storage_key"])


def downgrade() -> None:
    op.drop_constraint("uq_website_media_public_storage_key", "website_media", type_="unique")
    op.drop_column("website_media", "public_storage_key")
