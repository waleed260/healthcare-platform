"""Expand the controlled website section library."""
from alembic import op


revision = "0054_website_section_library"
down_revision = "0053_inventory_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE website_sections DROP CONSTRAINT IF EXISTS website_sections_section_type_check")
    op.execute("""
        ALTER TABLE website_sections
        ADD CONSTRAINT website_sections_section_type_check CHECK (section_type IN (
            'hero', 'banner', 'appointment_cta', 'lead_form', 'doctor_profile', 'services',
            'pricing', 'faq', 'testimonials', 'results', 'statistics', 'hours', 'location',
            'contact', 'about', 'legal'
        ))
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE website_sections DROP CONSTRAINT IF EXISTS website_sections_section_type_check")
    op.execute("""
        ALTER TABLE website_sections
        ADD CONSTRAINT website_sections_section_type_check CHECK (section_type IN (
            'hero', 'appointment_cta', 'doctor_profile', 'services', 'faq', 'hours', 'location', 'about', 'legal'
        ))
    """)
