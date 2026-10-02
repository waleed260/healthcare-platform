"""Add specialty enablement, lead CRM, and patient billing foundations."""

from alembic import op
import sqlalchemy as sa


revision = "0046_blueprint_core_foundations"
down_revision = "0045_access_token_tenant_fk"
branch_labels = None
depends_on = None


def _rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY {table}_tenant_policy ON {table}
        USING (clinic_id = current_setting('app.clinic_id', true)::uuid)
        WITH CHECK (clinic_id = current_setting('app.clinic_id', true)::uuid)
    """)


def upgrade() -> None:
    op.execute("""
        CREATE TABLE specialties (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            code text NOT NULL UNIQUE,
            name text NOT NULL,
            description text NULL,
            status text NOT NULL DEFAULT 'active',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_specialties_status CHECK (status IN ('active', 'archived'))
        )
    """)
    op.execute("""
        INSERT INTO specialties (code, name, description) VALUES
          ('dental', 'Dental', 'Dental care and oral health workflows'),
          ('hair', 'Hair Aesthetics / Transplant', 'Hair restoration and transplant workflows'),
          ('skin', 'Skin / Aesthetics', 'Skin, injectable, laser, and aesthetics workflows'),
          ('dermatology', 'Dermatology', 'Dermatology and prescription workflows')
        ON CONFLICT (code) DO NOTHING
    """)
    op.execute("""
        CREATE TABLE clinic_specialties (
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            specialty_id uuid NOT NULL REFERENCES specialties(id) ON DELETE RESTRICT,
            status text NOT NULL DEFAULT 'active',
            enabled_at timestamptz NOT NULL DEFAULT now(),
            archived_at timestamptz NULL,
            version integer NOT NULL DEFAULT 1,
            PRIMARY KEY (clinic_id, specialty_id),
            CONSTRAINT ck_clinic_specialties_status CHECK (status IN ('active', 'disabled'))
        )
    """)
    op.execute("""
        CREATE TABLE user_specialty_scopes (
            clinic_id uuid NOT NULL,
            user_id uuid NOT NULL,
            specialty_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (clinic_id, user_id, specialty_id),
            FOREIGN KEY (clinic_id, user_id) REFERENCES users (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, specialty_id) REFERENCES clinic_specialties (clinic_id, specialty_id) ON DELETE CASCADE
        )
    """)
    op.execute("ALTER TABLE services ADD COLUMN specialty_id uuid NULL")
    op.execute("ALTER TABLE doctor_profiles ADD COLUMN specialty_id uuid NULL")
    op.execute("ALTER TABLE appointments ADD COLUMN specialty_id uuid NULL")
    for table in ("services", "doctor_profiles", "appointments"):
        op.execute(f"""
            ALTER TABLE {table}
            ADD CONSTRAINT fk_{table}_specialty_tenant
            FOREIGN KEY (clinic_id, specialty_id)
            REFERENCES clinic_specialties (clinic_id, specialty_id)
            ON DELETE RESTRICT
        """)

    op.execute("""
        CREATE TABLE leads (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            full_name text NOT NULL,
            normalized_email text NULL,
            normalized_phone text NULL,
            source text NOT NULL,
            campaign text NULL,
            specialty_id uuid NULL,
            requested_service_id uuid NULL,
            assigned_to_user_id uuid NULL,
            status text NOT NULL DEFAULT 'new',
            notes text NULL,
            appointment_id uuid NULL,
            converted_to_patient_id uuid NULL,
            lost_reason text NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            version integer NOT NULL DEFAULT 1,
            archived_at timestamptz NULL,
            CONSTRAINT ck_leads_status CHECK (status IN ('new', 'contacted', 'qualified', 'appointment_booked', 'visited', 'converted', 'lost')),
            FOREIGN KEY (clinic_id, specialty_id) REFERENCES clinic_specialties (clinic_id, specialty_id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, requested_service_id) REFERENCES services (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, assigned_to_user_id) REFERENCES users (clinic_id, id) ON DELETE SET NULL,
            FOREIGN KEY (clinic_id, appointment_id) REFERENCES appointments (clinic_id, id) ON DELETE SET NULL,
            FOREIGN KEY (clinic_id, converted_to_patient_id) REFERENCES patients (clinic_id, id) ON DELETE RESTRICT,
            CONSTRAINT uq_leads_clinic_id UNIQUE (clinic_id, id)
        )
    """)

    op.execute("""
        CREATE TABLE invoices (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE RESTRICT,
            patient_id uuid NOT NULL,
            invoice_number text NOT NULL,
            currency char(3) NOT NULL,
            subtotal_minor bigint NOT NULL DEFAULT 0,
            discount_minor bigint NOT NULL DEFAULT 0,
            tax_minor bigint NOT NULL DEFAULT 0,
            total_minor bigint NOT NULL DEFAULT 0,
            status text NOT NULL DEFAULT 'unpaid',
            issued_at timestamptz NOT NULL DEFAULT now(),
            notes text NULL,
            created_by_user_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            version integer NOT NULL DEFAULT 1,
            CONSTRAINT uq_invoices_number UNIQUE (clinic_id, invoice_number),
            CONSTRAINT uq_invoices_clinic_id UNIQUE (clinic_id, id),
            CONSTRAINT ck_invoices_status CHECK (status IN ('unpaid', 'partially_paid', 'paid', 'refunded', 'void')),
            CONSTRAINT ck_invoices_amounts CHECK (subtotal_minor >= 0 AND discount_minor >= 0 AND tax_minor >= 0 AND total_minor >= 0),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES patients (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, created_by_user_id) REFERENCES users (clinic_id, id) ON DELETE RESTRICT
        )
    """)
    op.execute("""
        CREATE TABLE invoice_lines (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            invoice_id uuid NOT NULL,
            service_id uuid NULL,
            description text NOT NULL,
            quantity integer NOT NULL DEFAULT 1,
            unit_price_minor bigint NOT NULL,
            tax_minor bigint NOT NULL DEFAULT 0,
            line_total_minor bigint NOT NULL,
            FOREIGN KEY (clinic_id, invoice_id) REFERENCES invoices (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, service_id) REFERENCES services (clinic_id, id) ON DELETE RESTRICT,
            CONSTRAINT ck_invoice_lines_amounts CHECK (quantity > 0 AND unit_price_minor >= 0 AND tax_minor >= 0 AND line_total_minor >= 0)
        )
    """)
    op.execute("""
        CREATE TABLE invoice_number_sequences (
            clinic_id uuid NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
            sequence_year integer NOT NULL,
            next_value bigint NOT NULL DEFAULT 1,
            PRIMARY KEY (clinic_id, sequence_year),
            CONSTRAINT ck_invoice_sequence_value CHECK (next_value > 0)
        )
    """)
    op.execute("""
        CREATE TABLE payments (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL,
            invoice_id uuid NOT NULL,
            amount_minor bigint NOT NULL,
            currency char(3) NOT NULL,
            method text NOT NULL,
            reference text NULL,
            paid_at timestamptz NOT NULL DEFAULT now(),
            recorded_by_user_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_payments_clinic_id UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, invoice_id) REFERENCES invoices (clinic_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (clinic_id, recorded_by_user_id) REFERENCES users (clinic_id, id) ON DELETE RESTRICT,
            CONSTRAINT ck_payments_amount CHECK (amount_minor > 0)
        )
    """)
    op.execute("""
        CREATE TABLE payment_allocations (
            clinic_id uuid NOT NULL,
            payment_id uuid NOT NULL,
            invoice_id uuid NOT NULL,
            amount_minor bigint NOT NULL,
            PRIMARY KEY (clinic_id, payment_id, invoice_id),
            FOREIGN KEY (clinic_id, payment_id) REFERENCES payments (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, invoice_id) REFERENCES invoices (clinic_id, id) ON DELETE RESTRICT,
            CONSTRAINT ck_payment_allocations_amount CHECK (amount_minor > 0)
        )
    """)
    op.execute("CREATE INDEX ix_leads_clinic_status ON leads (clinic_id, status, created_at DESC)")
    op.execute("CREATE INDEX ix_invoices_clinic_patient ON invoices (clinic_id, patient_id, issued_at DESC)")
    op.execute("CREATE INDEX ix_payments_clinic_invoice ON payments (clinic_id, invoice_id, paid_at DESC)")

    for table in ("clinic_specialties", "user_specialty_scopes", "leads", "invoices", "invoice_lines", "invoice_number_sequences", "payments", "payment_allocations"):
        _rls(table)

    for code, description in (
        ('specialty.read', 'Read enabled clinic specialties'),
        ('specialty.manage', 'Manage clinic specialty access'),
        ('lead.read', 'Read clinic leads'),
        ('lead.manage', 'Manage clinic leads'),
        ('billing.read', 'Read patient invoices and payments'),
        ('billing.manage', 'Create invoices and record payments'),
    ):
        op.execute(sa.text(
            "INSERT INTO permissions (code, description) "
            "VALUES (:code, :description) ON CONFLICT DO NOTHING"
        ).bindparams(code=code, description=description))
    for role in ('owner', 'manager'):
        op.execute(sa.text("""
            INSERT INTO role_permissions (role_id, permission_code)
            SELECT r.id, p.code FROM roles r CROSS JOIN permissions p
            WHERE r.name = :role AND p.code IN ('specialty.read', 'specialty.manage', 'lead.read', 'lead.manage', 'billing.read', 'billing.manage')
            ON CONFLICT DO NOTHING
        """).bindparams(role=role))
    for role in ('receptionist', 'doctor'):
        op.execute(sa.text("""
            INSERT INTO role_permissions (role_id, permission_code)
            SELECT r.id, p.code FROM roles r CROSS JOIN permissions p
            WHERE r.name = :role AND p.code IN ('specialty.read', 'lead.read', 'lead.manage', 'billing.read')
            ON CONFLICT DO NOTHING
        """).bindparams(role=role))
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON specialties, clinic_specialties, user_specialty_scopes, leads, invoices, invoice_lines, invoice_number_sequences, payments, payment_allocations TO healthcare_runtime")


def downgrade() -> None:
    for table in ('payment_allocations', 'payments', 'invoice_number_sequences', 'invoice_lines', 'invoices', 'leads', 'user_specialty_scopes', 'clinic_specialties'):
        op.execute(f"DROP TABLE IF EXISTS {table}")
    for table in ('appointments', 'doctor_profiles', 'services'):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS fk_{table}_specialty_tenant")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS specialty_id")
    op.execute("DROP TABLE IF EXISTS specialties")
