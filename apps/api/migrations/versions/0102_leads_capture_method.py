"""Separate CRM capture method from acquisition source on leads.

``source`` stays free-text and means *where the enquiry came from* (phone call, walk-in,
referral, website, social media, ...). The new ``capture_method`` records *how the lead entered
the CRM* and is constrained. Manual staff entry must never be labelled a website lead.

Existing rows are backfilled: anything previously stored with ``source = 'website'`` came from a
public form, so it is marked ``public_website_form`` (the custom-form variant cannot be told apart
retroactively from source alone); everything else is ``manual_staff_entry``.
"""
from alembic import op

revision = "0102_leads_capture_method"
down_revision = "0101_lead_convert_permission"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE leads ADD COLUMN capture_method text NOT NULL DEFAULT 'manual_staff_entry'")
    op.execute("""
        ALTER TABLE leads ADD CONSTRAINT ck_leads_capture_method
        CHECK (capture_method IN ('manual_staff_entry', 'public_website_form', 'custom_website_form', 'import', 'other'))
    """)
    op.execute("UPDATE leads SET capture_method = 'public_website_form' WHERE source = 'website'")


def downgrade() -> None:
    op.execute("ALTER TABLE leads DROP CONSTRAINT IF EXISTS ck_leads_capture_method")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS capture_method")
