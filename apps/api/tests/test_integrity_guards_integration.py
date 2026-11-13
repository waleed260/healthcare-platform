"""Migration 0094 evidence: the database itself refuses duplicate encounters per
appointment and duplicate live invoices per encounter, and the runtime role can
no longer rewrite ledger rows. Route-level checks were check-then-insert races."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from app.db.tenant import set_tenant_context

pytestmark = pytest.mark.integration


def _database_urls() -> tuple[str, str]:
    admin_url = os.getenv("TEST_ADMIN_DATABASE_URL")
    runtime_url = os.getenv("TEST_DATABASE_URL")
    if not admin_url or not runtime_url:
        pytest.skip("PostgreSQL integration URLs are not configured")
    return admin_url, runtime_url


def test_duplicate_encounter_and_invoice_are_rejected_by_the_database() -> None:
    admin_url, runtime_url = _database_urls()
    admin, runtime = create_engine(admin_url), create_engine(runtime_url)
    clinic, user, branch, patient, doctor_user, doctor, service, appointment, encounter = (uuid4() for _ in range(9))
    try:
        with admin.begin() as c:
            c.execute(text("INSERT INTO clinics (id, name, slug) VALUES (:id, 'Integrity Synthetic', :slug)"), {"id": clinic, "slug": f"integ-{clinic}"})
            c.execute(text("INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash, status) VALUES (:id, :clinic, :email, 'Op', 'x', 'active')"), {"id": user, "clinic": clinic, "email": f"op-{user}@example.test"})
            c.execute(text("INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash, status) VALUES (:id, :clinic, :email, 'Doc', 'x', 'active')"), {"id": doctor_user, "clinic": clinic, "email": f"doc-{doctor_user}@example.test"})
            c.execute(text("INSERT INTO branches (id, clinic_id, code, name, timezone) VALUES (:id, :clinic, 'MAIN', 'Main', 'UTC')"), {"id": branch, "clinic": clinic})
            c.execute(text("INSERT INTO patients (id, clinic_id, patient_number, full_name) VALUES (:id, :clinic, 'P-1', 'Pat')"), {"id": patient, "clinic": clinic})
            c.execute(text("INSERT INTO doctor_profiles (id, clinic_id, user_id, public_name, consultation_duration_minutes) VALUES (:id, :clinic, :user, 'Dr Who', 30)"), {"id": doctor, "clinic": clinic, "user": doctor_user})
            c.execute(text("INSERT INTO services (id, clinic_id, name, duration_minutes, approval_mode, price_mode, visibility) VALUES (:id, :clinic, 'Consult', 30, 'staff_approval', 'contact', 'public')"), {"id": service, "clinic": clinic})
            c.execute(text("""
                INSERT INTO appointments (id, clinic_id, branch_id, patient_id, doctor_id, service_id, reference, starts_at, ends_at, occupancy_start, occupancy_end, status, status_changed_at, idempotency_key, idempotency_body_hash)
                VALUES (:id, :clinic, :branch, :patient, :doctor, :service, 'A-1', now(), now() + interval '30 min', now(), now() + interval '30 min', 'in_consultation', now(), gen_random_uuid()::text, md5(random()::text))
            """), {"id": appointment, "clinic": clinic, "branch": branch, "patient": patient, "doctor": doctor, "service": service})

        encounter_sql = text("""
            INSERT INTO encounter_forms (id, clinic_id, patient_id, appointment_id, doctor_id, branch_id, encounter_type, created_by)
            VALUES (:id, :clinic, :patient, :appt, :doctor, :branch, 'general', :user)
        """)
        with runtime.begin() as c:
            set_tenant_context(c, clinic, user)
            c.execute(encounter_sql, {"id": encounter, "clinic": clinic, "patient": patient, "appt": appointment, "doctor": doctor, "branch": branch, "user": user})
        with pytest.raises(IntegrityError, match="uq_encounter_forms_active_appointment"):
            with runtime.begin() as c:
                set_tenant_context(c, clinic, user)
                c.execute(encounter_sql, {"id": uuid4(), "clinic": clinic, "patient": patient, "appt": appointment, "doctor": doctor, "branch": branch, "user": user})

        invoice_sql = text("""
            INSERT INTO invoices (clinic_id, patient_id, encounter_id, invoice_number, currency, subtotal_minor, discount_minor, tax_minor, total_minor, status, created_by_user_id)
            VALUES (:clinic, :patient, :enc, :number, 'PKR', 100, 0, 0, 100, :status, :user)
        """)
        with runtime.begin() as c:
            set_tenant_context(c, clinic, user)
            c.execute(invoice_sql, {"clinic": clinic, "patient": patient, "enc": encounter, "number": f"T-{uuid4()}", "status": "unpaid", "user": user})
        with pytest.raises(IntegrityError, match="uq_invoices_active_encounter"):
            with runtime.begin() as c:
                set_tenant_context(c, clinic, user)
                c.execute(invoice_sql, {"clinic": clinic, "patient": patient, "enc": encounter, "number": f"T-{uuid4()}", "status": "unpaid", "user": user})
        # A voided invoice does not block a replacement.
        with runtime.begin() as c:
            set_tenant_context(c, clinic, user)
            c.execute(invoice_sql, {"clinic": clinic, "patient": patient, "enc": encounter, "number": f"T-{uuid4()}", "status": "void", "user": user})
    finally:
        with admin.begin() as c:
            for table in ("invoices", "encounter_forms", "appointments", "services", "doctor_profiles", "patients", "branches", "users"):
                c.execute(text(f"DELETE FROM {table} WHERE clinic_id = :clinic"), {"clinic": clinic})
            c.execute(text("DELETE FROM clinics WHERE id = :clinic"), {"clinic": clinic})


def test_runtime_role_cannot_rewrite_ledger_rows() -> None:
    _, runtime_url = _database_urls()
    runtime = create_engine(runtime_url)
    for statement in ("DELETE FROM payments WHERE false", "UPDATE payments SET amount_minor = 0 WHERE false", "DELETE FROM appointment_history WHERE false", "DELETE FROM inventory_adjustments WHERE false"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            with runtime.begin() as c:
                c.execute(text(statement))
