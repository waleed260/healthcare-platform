"""Add per-page SEO controls and website redirects."""
from alembic import op

revision = "0060_website_seo_redirects"
down_revision = "0059_reusable_website_sections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE website_pages ADD COLUMN canonical_url text NULL")
    op.execute("ALTER TABLE website_pages ADD COLUMN noindex boolean NOT NULL DEFAULT false")
    op.execute("ALTER TABLE website_pages ADD COLUMN og_title text NULL")
    op.execute("ALTER TABLE website_pages ADD COLUMN og_description text NULL")
    op.execute("ALTER TABLE website_pages ADD COLUMN og_image_media_id uuid NULL")
    op.execute("""
        CREATE TABLE website_redirects (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            website_id uuid NOT NULL,
            from_path text NOT NULL CHECK (from_path LIKE '/%' AND length(from_path) <= 300),
            to_path text NOT NULL CHECK (length(to_path) <= 500),
            status_code integer NOT NULL DEFAULT 301 CHECK (status_code IN (301, 302)),
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_website_redirects_from UNIQUE (clinic_id, website_id, from_path),
            CONSTRAINT uq_website_redirects_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_website_redirects_loop CHECK (from_path <> to_path),
            FOREIGN KEY (clinic_id, website_id) REFERENCES websites (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("ALTER TABLE website_redirects ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE website_redirects FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY website_redirects_tenant_policy ON website_redirects USING (clinic_id = current_setting('app.clinic_id', true)::uuid) WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON website_redirects TO healthcare_runtime")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS website_redirects")
    for column in ("og_image_media_id", "og_description", "og_title", "noindex", "canonical_url"):
        op.execute(f"ALTER TABLE website_pages DROP COLUMN IF EXISTS {column}")
