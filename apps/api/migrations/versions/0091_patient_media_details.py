"""Enrich patient media with title/notes, broader kinds, and appointment link."""
from alembic import op


revision = "0091_patient_media_details"
down_revision = "0090_appointment_token_number"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE patient_media ADD COLUMN title text NULL")
    op.execute("ALTER TABLE patient_media ADD COLUMN notes text NULL")
    op.execute("ALTER TABLE patient_media ADD COLUMN appointment_id uuid NULL")
    op.execute("ALTER TABLE patient_media ADD CONSTRAINT ck_patient_media_title_len CHECK (title IS NULL OR char_length(title) <= 200)")
    op.execute("ALTER TABLE patient_media ADD CONSTRAINT ck_patient_media_notes_len CHECK (notes IS NULL OR char_length(notes) <= 2000)")
    op.execute("ALTER TABLE patient_media DROP CONSTRAINT ck_patient_media_kind")
    op.execute("ALTER TABLE patient_media ADD CONSTRAINT ck_patient_media_kind CHECK (media_kind IN ('before', 'after', 'other', 'xray', 'scan', 'lab', 'photo', 'document'))")
    op.execute("ALTER TABLE patient_media ADD CONSTRAINT fk_patient_media_appointment FOREIGN KEY (clinic_id, appointment_id) REFERENCES appointments (clinic_id, id) ON DELETE SET NULL")
    op.execute("CREATE INDEX ix_patient_media_appointment ON patient_media (clinic_id, appointment_id) WHERE appointment_id IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_patient_media_appointment")
    op.execute("ALTER TABLE patient_media DROP CONSTRAINT IF EXISTS fk_patient_media_appointment")
    op.execute("ALTER TABLE patient_media DROP CONSTRAINT ck_patient_media_kind")
    op.execute("ALTER TABLE patient_media ADD CONSTRAINT ck_patient_media_kind CHECK (media_kind IN ('before', 'after', 'other'))")
    op.execute("ALTER TABLE patient_media DROP CONSTRAINT IF EXISTS ck_patient_media_notes_len")
    op.execute("ALTER TABLE patient_media DROP CONSTRAINT IF EXISTS ck_patient_media_title_len")
    op.execute("ALTER TABLE patient_media DROP COLUMN IF EXISTS appointment_id")
    op.execute("ALTER TABLE patient_media DROP COLUMN IF EXISTS notes")
    op.execute("ALTER TABLE patient_media DROP COLUMN IF EXISTS title")
