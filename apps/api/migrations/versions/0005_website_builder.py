"""Create controlled website builder and publishing records."""
from alembic import op
import sqlalchemy as sa

revision = "0005_website_builder"
down_revision = "0004_catalog_onboarding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for code, description in (("website.read", "Read website drafts and versions"), ("website.edit", "Edit website drafts"), ("website.publish", "Publish website versions")):
        op.execute(sa.text("INSERT INTO permissions (code, description) VALUES (:code, :description) ON CONFLICT (code) DO NOTHING").bindparams(code=code, description=description))
    for role in ("owner", "manager"):
        op.execute(sa.text("""
            INSERT INTO role_permissions (role_id, permission_code)
            SELECT r.id, p.code FROM roles r CROSS JOIN permissions p
            WHERE r.name = :role AND p.code IN ('website.read', 'website.edit', 'website.publish')
        """).bindparams(role=role))
    op.execute(sa.text("""
        INSERT INTO role_permissions (role_id, permission_code)
        SELECT r.id, p.code FROM roles r CROSS JOIN permissions p
        WHERE r.name = 'website_editor' AND p.code IN ('website.read', 'website.edit')
    """))
    op.execute("""
        CREATE TABLE websites (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            name text NOT NULL,
            template_key text NOT NULL CHECK (template_key IN ('calm_clinic', 'editorial_practice', 'warm_studio')),
            brand jsonb NOT NULL DEFAULT '{}'::jsonb,
            status text NOT NULL DEFAULT 'draft',
            draft_version_id uuid NULL,
            live_version_id uuid NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz NULL,
            version integer NOT NULL DEFAULT 1,
            CONSTRAINT uq_websites_clinic_id UNIQUE (clinic_id, id)
        )
    """)
    op.execute("""
        CREATE TABLE website_versions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            website_id uuid NOT NULL,
            version_number integer NOT NULL,
            schema_version integer NOT NULL DEFAULT 1,
            snapshot jsonb NOT NULL,
            checksum char(64) NOT NULL,
            created_by uuid NULL,
            published_at timestamptz NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_website_versions_number UNIQUE (clinic_id, website_id, version_number),
            CONSTRAINT uq_website_versions_clinic_id UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, website_id) REFERENCES websites (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("ALTER TABLE websites ADD CONSTRAINT fk_websites_draft_version FOREIGN KEY (clinic_id, draft_version_id) REFERENCES website_versions (clinic_id, id)")
    op.execute("ALTER TABLE websites ADD CONSTRAINT fk_websites_live_version FOREIGN KEY (clinic_id, live_version_id) REFERENCES website_versions (clinic_id, id)")
    op.execute("""
        CREATE TABLE website_pages (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            website_id uuid NOT NULL,
            slug text NOT NULL,
            title text NOT NULL,
            seo_title text NULL,
            seo_description text NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_website_pages_slug UNIQUE (clinic_id, website_id, slug),
            CONSTRAINT uq_website_pages_clinic_id UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, website_id) REFERENCES websites (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE website_sections (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            page_id uuid NOT NULL,
            section_type text NOT NULL CHECK (section_type IN ('hero', 'appointment_cta', 'doctor_profile', 'services', 'faq', 'hours', 'location', 'about', 'legal')),
            layout_key text NOT NULL,
            position integer NOT NULL CHECK (position >= 0),
            content jsonb NOT NULL DEFAULT '{}'::jsonb,
            is_visible boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_website_sections_position UNIQUE (clinic_id, page_id, position),
            CONSTRAINT uq_website_sections_clinic_id UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, page_id) REFERENCES website_pages (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE website_media (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            storage_key text NOT NULL,
            alt_text text NOT NULL,
            mime_type text NOT NULL,
            scan_status text NOT NULL DEFAULT 'pending_scan',
            is_public boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_website_media_clinic_id UNIQUE (clinic_id, id)
        )
    """)
    op.execute("""
        CREATE TABLE domain_verifications (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            hostname text NOT NULL,
            expected_dns_proof text NOT NULL,
            observed_status text NOT NULL DEFAULT 'pending',
            certificate_status text NOT NULL DEFAULT 'not_requested',
            checked_at timestamptz NULL,
            failure_reason text NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_domain_verifications_hostname UNIQUE (hostname),
            CONSTRAINT uq_domain_verifications_clinic_id UNIQUE (clinic_id, id)
        )
    """)
    for table in ("websites", "website_versions", "website_pages", "website_sections", "website_media", "domain_verifications"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(sa.text(f"""
            CREATE POLICY {table}_tenant_policy ON {table}
            USING (clinic_id = current_setting('app.clinic_id', true)::uuid)
            WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)
        """))
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON websites, website_versions, website_pages, website_sections, website_media, domain_verifications TO healthcare_runtime")


def downgrade() -> None:
    for table in ("domain_verifications", "website_media", "website_sections", "website_pages", "website_versions", "websites"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
