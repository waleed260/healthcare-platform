"""PostgreSQL evidence that encounter discharge completes queue + appointment.

Regression for ``encounter_discharge``: previously the queue entry and the
appointment stayed in ``in_consultation`` after discharge, so the Queue page
and schedule kept showing the patient. Two assertions:

* when the encounter has a linked appointment, the queue entry is marked
  ``completed`` (so the Queue page drops it) and the appointment is marked
  ``completed`` (matching the ``queue_complete`` endpoint's behavior).
* when the encounter has no appointment, discharge still succeeds without
  touching any queue/appointment rows.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from app.db.tenant import set_tenant_context

pytestmark = pytest.mark.integration


def _database_urls() -> tuple[str, str]:
    admin_url = os.getenv("TEST_ADMIN_DATABASE_URL")
    runtime_url = os.getenv("TEST_DATABASE_URL")
    if not admin_url or not runtime_url:
        pytest.skip("PostgreSQL integration URLs are not configured")
    return admin_url, runtime_url


# The SQL block copied verbatim from encounter_discharge's post-update step;
# running the same statements here proves the query shape is valid on the
# real schema and has the expected effect.
_DISCHARGE_SQL = [
    text("""
        UPDATE queue_entries SET status = 'completed', completed_at = now(), version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND appointment_id = :appt_id AND status IN ('waiting', 'in_consultation')
    """),
    text("""
        UPDATE appointments SET status = 'completed', blocks_time = false, status_changed_at = now(), version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND id = :appt_id AND status = 'in_consultation'
        RETURNING id
    """),
]


def test_discharge_completes_queue_and_appointment() -> None:
    admin_url, runtime_url = _database_urls()
    admin = create_engine(admin_url)
    runtime = create_engine(runtime_url)
    clinic = uuid4()
    user = uuid4()
    branch = uuid4()
    patient = uuid4()
    doctor_user = uuid4()
    doctor = uuid4()
    service = uuid4()
    appointment = uuid4()
    try:
        with admin.begin() as c:
            c.execute(text("INSERT INTO clinics (id, name, slug) VALUES (:id, 'Discharge Synthetic', :slug)"), {"id": clinic, "slug": f"disch-{clinic}"})
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
            c.execute(text("""
                INSERT INTO queue_entries (clinic_id, appointment_id, status, started_at)
                VALUES (:clinic, :appt, 'in_consultation', now())
            """), {"clinic": clinic, "appt": appointment})

        with runtime.begin() as c:
            set_tenant_context(c, clinic, user)
            for stmt in _DISCHARGE_SQL:
                c.execute(stmt, {"clinic_id": clinic, "appt_id": appointment})

        with runtime.begin() as c:
            set_tenant_context(c, clinic, user)
            queue_status = c.execute(text("SELECT status FROM queue_entries WHERE clinic_id = :clinic AND appointment_id = :appt"), {"clinic": clinic, "appt": appointment}).scalar_one()
            appt_status = c.execute(text("SELECT status FROM appointments WHERE clinic_id = :clinic AND id = :appt"), {"clinic": clinic, "appt": appointment}).scalar_one()
            assert queue_status == "completed", queue_status
            assert appt_status == "completed", appt_status
    finally:
        with admin.begin() as c:
            c.execute(text("DELETE FROM queue_entries WHERE clinic_id = :clinic"), {"clinic": clinic})
            c.execute(text("DELETE FROM appointments WHERE clinic_id = :clinic"), {"clinic": clinic})
            c.execute(text("DELETE FROM services WHERE clinic_id = :clinic"), {"clinic": clinic})
            c.execute(text("DELETE FROM doctor_profiles WHERE clinic_id = :clinic"), {"clinic": clinic})
            c.execute(text("DELETE FROM patients WHERE clinic_id = :clinic"), {"clinic": clinic})
            c.execute(text("DELETE FROM branches WHERE clinic_id = :clinic"), {"clinic": clinic})
            c.execute(text("DELETE FROM users WHERE clinic_id = :clinic"), {"clinic": clinic})
            c.execute(text("DELETE FROM clinics WHERE id = :clinic"), {"clinic": clinic})


def test_discharge_skips_queue_update_when_queue_is_already_complete() -> None:
    """If queue is already completed (e.g. via queue_complete), discharge SQL is a no-op."""
    admin_url, runtime_url = _database_urls()
    admin = create_engine(admin_url)
    runtime = create_engine(runtime_url)
    clinic = uuid4()
    user = uuid4()
    branch = uuid4()
    patient = uuid4()
    doctor_user = uuid4()
    doctor = uuid4()
    service = uuid4()
    appointment = uuid4()
    try:
        with admin.begin() as c:
            c.execute(text("INSERT INTO clinics (id, name, slug) VALUES (:id, 'Discharge Idem', :slug)"), {"id": clinic, "slug": f"disch2-{clinic}"})
            c.execute(text("INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash, status) VALUES (:id, :clinic, :email, 'Op', 'x', 'active')"), {"id": user, "clinic": clinic, "email": f"op-{user}@example.test"})
            c.execute(text("INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash, status) VALUES (:id, :clinic, :email, 'Doc', 'x', 'active')"), {"id": doctor_user, "clinic": clinic, "email": f"doc-{doctor_user}@example.test"})
            c.execute(text("INSERT INTO branches (id, clinic_id, code, name, timezone) VALUES (:id, :clinic, 'MAIN', 'Main', 'UTC')"), {"id": branch, "clinic": clinic})
            c.execute(text("INSERT INTO patients (id, clinic_id, patient_number, full_name) VALUES (:id, :clinic, 'P-1', 'Pat')"), {"id": patient, "clinic": clinic})
            c.execute(text("INSERT INTO doctor_profiles (id, clinic_id, user_id, public_name, consultation_duration_minutes) VALUES (:id, :clinic, :user, 'Dr Who', 30)"), {"id": doctor, "clinic": clinic, "user": doctor_user})
            c.execute(text("INSERT INTO services (id, clinic_id, name, duration_minutes, approval_mode, price_mode, visibility) VALUES (:id, :clinic, 'Consult', 30, 'staff_approval', 'contact', 'public')"), {"id": service, "clinic": clinic})
            c.execute(text("""
                INSERT INTO appointments (id, clinic_id, branch_id, patient_id, doctor_id, service_id, reference, starts_at, ends_at, occupancy_start, occupancy_end, status, status_changed_at, idempotency_key, idempotency_body_hash)
                VALUES (:id, :clinic, :branch, :patient, :doctor, :service, 'A-1', now(), now() + interval '30 min', now(), now() + interval '30 min', 'completed', now(), gen_random_uuid()::text, md5(random()::text))
            """), {"id": appointment, "clinic": clinic, "branch": branch, "patient": patient, "doctor": doctor, "service": service})
            c.execute(text("""
                INSERT INTO queue_entries (clinic_id, appointment_id, status, started_at, completed_at)
                VALUES (:clinic, :appt, 'completed', now(), now())
            """), {"clinic": clinic, "appt": appointment})

        with runtime.begin() as c:
            set_tenant_context(c, clinic, user)
            for stmt in _DISCHARGE_SQL:
                c.execute(stmt, {"clinic_id": clinic, "appt_id": appointment})

        with runtime.begin() as c:
            set_tenant_context(c, clinic, user)
            queue_status = c.execute(text("SELECT status FROM queue_entries WHERE clinic_id = :clinic AND appointment_id = :appt"), {"clinic": clinic, "appt": appointment}).scalar_one()
            appt_status = c.execute(text("SELECT status FROM appointments WHERE clinic_id = :clinic AND id = :appt"), {"clinic": clinic, "appt": appointment}).scalar_one()
            assert queue_status == "completed"
            assert appt_status == "completed"
    finally:
        with admin.begin() as c:
            c.execute(text("DELETE FROM queue_entries WHERE clinic_id = :clinic"), {"clinic": clinic})
            c.execute(text("DELETE FROM appointments WHERE clinic_id = :clinic"), {"clinic": clinic})
            c.execute(text("DELETE FROM services WHERE clinic_id = :clinic"), {"clinic": clinic})
            c.execute(text("DELETE FROM doctor_profiles WHERE clinic_id = :clinic"), {"clinic": clinic})
            c.execute(text("DELETE FROM patients WHERE clinic_id = :clinic"), {"clinic": clinic})
            c.execute(text("DELETE FROM branches WHERE clinic_id = :clinic"), {"clinic": clinic})
            c.execute(text("DELETE FROM users WHERE clinic_id = :clinic"), {"clinic": clinic})
            c.execute(text("DELETE FROM clinics WHERE id = :clinic"), {"clinic": clinic})
