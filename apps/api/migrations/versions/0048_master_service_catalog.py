"""Add platform-owned service templates and clinic-copy provenance."""
from alembic import op
import sqlalchemy as sa

revision = "0048_master_service_catalog"
down_revision = "0047_treatment_plans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE service_templates (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            specialty_id uuid NULL REFERENCES specialties (id) ON DELETE RESTRICT,
            code text NOT NULL UNIQUE,
            name text NOT NULL,
            category text NULL,
            subcategory text NULL,
            short_description text NULL,
            full_description text NULL,
            duration_minutes integer NOT NULL CHECK (duration_minutes > 0),
            buffer_before_minutes integer NOT NULL DEFAULT 0 CHECK (buffer_before_minutes >= 0),
            buffer_after_minutes integer NOT NULL DEFAULT 0 CHECK (buffer_after_minutes >= 0),
            price_mode text NOT NULL DEFAULT 'contact',
            online_booking_allowed boolean NOT NULL DEFAULT false,
            consultation_required boolean NOT NULL DEFAULT true,
            sessions_count integer NULL CHECK (sessions_count IS NULL OR sessions_count > 0),
            follow_up_required boolean NOT NULL DEFAULT false,
            follow_up_days integer NULL CHECK (follow_up_days IS NULL OR follow_up_days > 0),
            patient_instructions text NULL,
            status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.add_column("services", sa.Column("source_template_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_services_source_template", "services", "service_templates", ["source_template_id"], ["id"], ondelete="SET NULL")
    op.add_column("services", sa.Column("subcategory", sa.Text(), nullable=True))
    op.add_column("services", sa.Column("online_booking_allowed", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("services", sa.Column("consultation_required", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("services", sa.Column("sessions_count", sa.Integer(), nullable=True))
    op.add_column("services", sa.Column("follow_up_required", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("services", sa.Column("follow_up_days", sa.Integer(), nullable=True))
    op.add_column("services", sa.Column("patient_instructions", sa.Text(), nullable=True))
    op.add_column("services", sa.Column("featured", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("services", sa.Column("slug", sa.Text(), nullable=True))
    op.execute("CREATE INDEX ix_service_templates_specialty ON service_templates (specialty_id, status, name)")
    op.execute("CREATE INDEX ix_services_source_template ON services (clinic_id, source_template_id)")
    op.execute("GRANT SELECT ON service_templates TO healthcare_runtime")


def downgrade() -> None:
    op.drop_index("ix_services_source_template", table_name="services")
    op.drop_index("ix_service_templates_specialty", table_name="service_templates")
    op.drop_constraint("fk_services_source_template", "services", type_="foreignkey")
    for column in ("slug", "featured", "patient_instructions", "follow_up_days", "follow_up_required", "sessions_count", "consultation_required", "online_booking_allowed", "subcategory", "source_template_id"):
        op.drop_column("services", column)
    op.drop_table("service_templates")
