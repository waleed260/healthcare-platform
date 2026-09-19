"""Encrypt private patient-document filenames without breaking an old API.

Requirement IDs: SEC-011, CRM-010, REL-003.
"""
from alembic import op


revision = "0041_encrypt_private_document_metadata"
down_revision = "0040_crm_care_team_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep ``original_filename`` for one rolling-deploy window. New code stores
    # only a generic extension-based name there and keeps the real safe display
    # name encrypted in the new column.
    op.execute("ALTER TABLE patient_documents ADD COLUMN original_filename_ciphertext text NULL")
    op.execute("""
        INSERT INTO background_jobs (clinic_id, job_key, job_type, status)
        SELECT clinic_id,
               'document-metadata-encrypt:' || id::text,
               'document_metadata_encrypt',
               'queued'
        FROM patient_documents
        WHERE original_filename_ciphertext IS NULL
        ON CONFLICT (clinic_id, job_key) DO NOTHING
    """)


def downgrade() -> None:
    # Ciphertext cannot safely be transformed back into plaintext in a database
    # migration. The generic legacy filename remains usable for an application
    # rollback, while the column can be removed only after queued jobs are gone.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM background_jobs
                WHERE job_type = 'document_metadata_encrypt'
                  AND status IN ('queued', 'running')
            ) THEN
                RAISE EXCEPTION 'cannot downgrade while document metadata encryption jobs are pending';
            END IF;
        END $$;
    """)
    op.execute("DELETE FROM background_jobs WHERE job_type = 'document_metadata_encrypt'")
    op.execute("ALTER TABLE patient_documents DROP COLUMN original_filename_ciphertext")
