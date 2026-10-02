"""Add website form builder, blog posts, and moderated testimonials."""
from alembic import op

revision = "0061_website_forms_blog_testimonials"
down_revision = "0060_website_seo_redirects"
branch_labels = None
depends_on = None

TABLES = ("website_forms", "website_posts", "website_testimonials")


def upgrade() -> None:
    op.execute("""
        CREATE TABLE website_forms (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            name text NOT NULL,
            fields jsonb NOT NULL,
            action text NOT NULL DEFAULT 'lead' CHECK (action IN ('lead', 'appointment_request')),
            specialty_id uuid NULL REFERENCES specialties(id) ON DELETE SET NULL,
            branch_id uuid NULL,
            notify_user_ids uuid[] NOT NULL DEFAULT '{}',
            success_message text NOT NULL DEFAULT 'Thanks, we will be in touch shortly.',
            status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_website_forms_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT uq_website_forms_name UNIQUE (clinic_id, name),
            FOREIGN KEY (clinic_id, branch_id) REFERENCES branches (clinic_id, id) ON DELETE SET NULL (branch_id)
        )
    """)
    op.execute("""
        CREATE TABLE website_posts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            slug text NOT NULL CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
            title text NOT NULL,
            excerpt text NOT NULL DEFAULT '',
            body text NOT NULL DEFAULT '',
            status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'archived')),
            published_at timestamptz NULL,
            seo_title text NULL,
            seo_description text NULL,
            author_user_id uuid NULL,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_website_posts_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT uq_website_posts_slug UNIQUE (clinic_id, slug)
        )
    """)
    op.execute("CREATE INDEX ix_website_posts_published ON website_posts (clinic_id, published_at DESC) WHERE status = 'published'")
    op.execute("""
        CREATE TABLE website_testimonials (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            author_name text NOT NULL,
            rating integer NOT NULL CHECK (rating BETWEEN 1 AND 5),
            body text NOT NULL,
            source text NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'patient')),
            consent_confirmed boolean NOT NULL DEFAULT false,
            status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
            moderated_by uuid NULL,
            moderated_at timestamptz NULL,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_website_testimonials_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_testimonial_consent CHECK (status <> 'approved' OR consent_confirmed)
        )
    """)
    op.execute("CREATE INDEX ix_website_testimonials_status ON website_testimonials (clinic_id, status, created_at DESC)")
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_tenant_policy ON {table} USING (clinic_id = current_setting('app.clinic_id', true)::uuid) WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON website_forms, website_posts, website_testimonials TO healthcare_runtime")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table}")
