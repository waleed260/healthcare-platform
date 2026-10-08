"""Expand website_sections section_type CHECK constraint to include all supported types."""
from alembic import op

revision = "0021_expand_section_types"
down_revision = "0020_public_rate_limits"
branch_labels = None
depends_on = None

ALLOWED_TYPES = (
    "hero", "banner", "appointment_cta", "lead_form", "doctor_profile",
    "services", "pricing", "faq", "testimonials", "results", "statistics",
    "hours", "location", "contact", "about", "legal",
    "timeline", "process", "steps", "gallery", "video", "comparison",
    "team", "care_team",
)


def upgrade() -> None:
    op.execute("ALTER TABLE website_sections DROP CONSTRAINT IF EXISTS website_sections_section_type_check")
    type_list = ", ".join(f"'{t}'" for t in ALLOWED_TYPES)
    op.execute(f"ALTER TABLE website_sections ADD CONSTRAINT website_sections_section_type_check CHECK (section_type IN ({type_list}))")


def downgrade() -> None:
    op.execute("ALTER TABLE website_sections DROP CONSTRAINT IF EXISTS website_sections_section_type_check")
    op.execute("ALTER TABLE website_sections ADD CONSTRAINT website_sections_section_type_check CHECK (section_type IN ('hero', 'appointment_cta', 'doctor_profile', 'services', 'faq', 'hours', 'location', 'about', 'legal'))")
