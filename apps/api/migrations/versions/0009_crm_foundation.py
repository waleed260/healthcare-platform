"""Create tenant-scoped CRM records, notes, tags, consent, and merge history."""
from alembic import op
import sqlalchemy as sa

revision = "0009_crm_foundation"
down_revision = "0008_operations_commands"
branch_labels = None
depends_on = None


def upgrade() -> None:
    permissions = (
        ("patient.read", "Read basic patient records"),
        ("patient.create", "Create patient records"),
        ("patient.update", "Update patient records"),
        ("patient.archive", "Archive patient records"),
        ("patient.export", "Export patient records"),
        ("patient.note.read", "Read general patient notes"),
        ("patient.note.write", "Write general patient notes"),
        ("patient.private_note.read", "Read private doctor notes"),
        ("patient.private_note.write", "Write private doctor notes"),
        ("consent.read", "Read consent records"),
        ("consent.manage", "Manage consent records"),
    )
    for code, description in permissions:
        op.execute(sa.text("INSERT INTO permissions (code, description) VALUES (:code, :description) ON CONFLICT (code) DO NOTHING").bindparams(code=code, description=description))
    role_codes = {
        "owner": [code for code, _ in permissions],
        "manager": ["patient.read", "patient.create", "patient.update", "patient.archive", "patient.note.read", "patient.note.write", "consent.read", "consent.manage"],
        "doctor": ["patient.read", "patient.create", "patient.update", "patient.note.read", "patient.note.write", "patient.private_note.read", "patient.private_note.write", "consent.read"],
        "receptionist": ["patient.read", "patient.create", "patient.update", "patient.note.read", "patient.note.write", "consent.read"],
    }
    for role, codes in role_codes.items():
        for code in codes:
            op.execute(sa.text("""
                INSERT INTO role_permissions (role_id, permission_code)
                SELECT r.id, :code FROM roles r
                WHERE r.name = :role
                ON CONFLICT DO NOTHING
            """).bindparams(role=role, code=code))

    op.add_column("patients", sa.Column("duplicate_of", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_patients_duplicate_of_tenant", "patients", "patients", ["clinic_id", "duplicate_of"], ["clinic_id", "id"], ondelete="RESTRICT")

    op.execute("""
        CREATE TABLE patient_contacts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            patient_id uuid NOT NULL,
            contact_type text NOT NULL,
            value text NOT NULL,
            normalized_value text NOT NULL,
            is_primary boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_patient_contacts_clinic_id UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES patients (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE tags (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            name text NOT NULL,
            normalized_name text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_tags_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT uq_tags_clinic_name UNIQUE (clinic_id, normalized_name),
            FOREIGN KEY (clinic_id) REFERENCES clinics (id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE patient_tags (
            clinic_id uuid NOT NULL,
            patient_id uuid NOT NULL,
            tag_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (clinic_id, patient_id, tag_id),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES patients (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, tag_id) REFERENCES tags (clinic_id, id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE patient_notes (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            patient_id uuid NOT NULL,
            author_user_id uuid NOT NULL,
            note_type text NOT NULL DEFAULT 'general',
            visibility text NOT NULL DEFAULT 'clinic',
            body text NOT NULL,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz NULL,
            CONSTRAINT uq_patient_notes_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_patient_notes_visibility CHECK (visibility IN ('clinic', 'private_doctor')),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES patients (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, author_user_id) REFERENCES users (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    op.execute("""
        CREATE TABLE consent_records (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            patient_id uuid NOT NULL,
            consent_type text NOT NULL,
            status text NOT NULL,
            version text NOT NULL,
            recorded_by_user_id uuid,
            recorded_at timestamptz NOT NULL DEFAULT now(),
            withdrawn_at timestamptz NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            CONSTRAINT uq_consent_records_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_consent_records_status CHECK (status IN ('granted', 'withdrawn', 'declined')),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES patients (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, recorded_by_user_id) REFERENCES users (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    op.execute("""
        CREATE TABLE patient_merge_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            source_patient_id uuid NOT NULL,
            target_patient_id uuid NOT NULL,
            actor_user_id uuid NOT NULL,
            reason text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_patient_merge_events_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_patient_merge_distinct CHECK (source_patient_id <> target_patient_id),
            FOREIGN KEY (clinic_id, source_patient_id) REFERENCES patients (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, target_patient_id) REFERENCES patients (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, actor_user_id) REFERENCES users (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    for table in ("patient_contacts", "tags", "patient_tags", "patient_notes", "consent_records", "patient_merge_events"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(sa.text(f"CREATE POLICY {table}_tenant_policy ON {table} USING (clinic_id = current_setting('app.clinic_id', true)::uuid) WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)"))
    op.execute("CREATE INDEX ix_patients_clinic_search ON patients (clinic_id, normalized_phone, normalized_email, archived_at)")
    op.execute("CREATE INDEX ix_patient_notes_patient ON patient_notes (clinic_id, patient_id, archived_at, created_at)")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON patients, patient_contacts, tags, patient_tags, patient_notes, consent_records, patient_merge_events TO healthcare_runtime")


def downgrade() -> None:
    op.drop_index("ix_patient_notes_patient", table_name="patient_notes")
    op.drop_index("ix_patients_clinic_search", table_name="patients")
    for table in ("patient_merge_events", "consent_records", "patient_notes", "patient_tags", "tags", "patient_contacts"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
    op.drop_constraint("fk_patients_duplicate_of_tenant", "patients", type_="foreignkey")
    op.drop_column("patients", "duplicate_of")
