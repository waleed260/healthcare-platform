"""Lead-originated appointment booking must allocate and persist the SAME canonical token as a
normal booking. Regression for the reported "appointment booked from a lead has no token".

The token was never actually missing server-side (``create_internal_booking`` allocates it from
``appointment_token_sequences`` regardless of ``lead_id``); the bug was purely that the leads-page
drawer closed before its token screen rendered. These tests lock the backend contract: a
lead-originated booking returns and persists a ``token_number``, keeps ``lead_id`` and advances the
lead, and a following non-lead booking at the same branch/date draws the next token from the same
sequence (shared allocation, non-lead path unaffected). Auto-skips without the integration DB URLs.
"""
import os
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session as OrmSession

from app.db.tenant import set_tenant_context
from app.modules.appointments import routes as appointment_routes
from app.modules.appointments.schemas import InternalBookingRequest


pytestmark = pytest.mark.integration


def _engines():
    admin_url = os.getenv("TEST_ADMIN_DATABASE_URL")
    runtime_url = os.getenv("TEST_DATABASE_URL")
    if not admin_url or not runtime_url:
        pytest.skip("PostgreSQL integration URLs are not configured")
    return create_engine(admin_url), create_engine(runtime_url, connect_args={"cursor_factory": psycopg.ClientCursor})


@pytest.fixture
def bookable(monkeypatch):
    admin, runtime = _engines()
    ids = {k: uuid4() for k in ("clinic", "user", "branch", "service", "doctor", "lead")}
    try:
        with admin.begin() as c:
            p = {**ids, "slug": f"token-{ids['clinic']}", "email": f"token-{ids['user']}@example.test"}
            c.execute(text("INSERT INTO clinics (id, name, slug) VALUES (:clinic, 'Token Clinic', :slug)"), p)
            c.execute(text("INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash) VALUES (:user, :clinic, :email, 'Staff', 'unused')"), p)
            c.execute(text("INSERT INTO branches (id, clinic_id, code, name, status, timezone) VALUES (:branch, :clinic, 'TKN', 'Token Branch', 'active', 'UTC')"), p)
            # Open every weekday all day so any future slot is within branch hours.
            for weekday in range(7):
                c.execute(text("INSERT INTO branch_hours (clinic_id, branch_id, weekday, opens_at, closes_at, is_closed) VALUES (:clinic, :branch, :wd, '00:00', '23:59', false)"), {**p, "wd": weekday})
            c.execute(text("INSERT INTO services (id, clinic_id, name, duration_minutes, status) VALUES (:service, :clinic, 'Consult', 30, 'active')"), p)
            c.execute(text("INSERT INTO branch_services (clinic_id, branch_id, service_id) VALUES (:clinic, :branch, :service)"), p)
            c.execute(text("INSERT INTO doctor_profiles (id, clinic_id, public_name, status) VALUES (:doctor, :clinic, 'Dr Token', 'active')"), p)
            c.execute(text("INSERT INTO branch_doctors (clinic_id, branch_id, doctor_id) VALUES (:clinic, :branch, :doctor)"), p)
            c.execute(text("INSERT INTO doctor_services (clinic_id, doctor_id, service_id) VALUES (:clinic, :doctor, :service)"), p)
            c.execute(text("INSERT INTO leads (id, clinic_id, full_name, source, status) VALUES (:lead, :clinic, 'Prospect', 'call', 'qualified')"), p)

        session = OrmSession(bind=runtime)
        monkeypatch.setattr(appointment_routes, "_staff_authorized", lambda db, token, permission, branch_id=None: (set_tenant_context(db, ids["clinic"], ids["user"]), {"clinic_id": ids["clinic"], "user_id": ids["user"]})[1])
        monkeypatch.setattr(appointment_routes, "_csrf", lambda *a, **k: None)
        yield session, ids
        session.close()
    finally:
        with admin.begin() as c:
            for table in ("appointment_token_sequences", "appointment_history", "appointments", "lead_stage_history",
                          "leads", "patients", "doctor_services", "branch_doctors", "doctor_profiles",
                          "branch_services", "branch_hours", "services", "branches", "users"):
                c.execute(text(f"DELETE FROM {table} WHERE clinic_id = :c"), {"c": ids["clinic"]})
            c.execute(text("DELETE FROM clinics WHERE id = :c"), {"c": ids["clinic"]})
        admin.dispose(); runtime.dispose()


def _book(session, ids, *, lead_id, full_name):
    slot = (datetime.now(timezone.utc) + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    payload = InternalBookingRequest(branch_id=ids["branch"], doctor_id=ids["doctor"], service_id=ids["service"],
                                     starts_at=slot, full_name=full_name, phone="+923001234567", lead_id=lead_id)
    req = SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())))
    return appointment_routes.create_internal_booking(payload, req, db=session, session_token="x", csrf_token="x", idempotency_key=f"idem-{uuid4()}")


def test_lead_booking_allocates_and_persists_canonical_token(bookable):
    session, ids = bookable
    result = _book(session, ids, lead_id=ids["lead"], full_name="Lead Patient")["data"]
    # Token is in the response.
    assert isinstance(result["token_number"], int) and result["token_number"] >= 1
    first_token = result["token_number"]
    # The booking committed, which cleared the transaction-local tenant context; re-set it so the
    # verification reads run under RLS as this clinic.
    set_tenant_context(session, ids["clinic"], ids["user"])
    # Token + lead link are persisted on the appointment row (serialization/persistence proof).
    row = session.execute(text(
        "SELECT token_number, lead_id FROM appointments WHERE clinic_id = :c AND reference = :ref"
    ), {"c": ids["clinic"], "ref": result["reference"]}).mappings().one()
    assert row["token_number"] == first_token
    assert row["lead_id"] == ids["lead"]
    # The lead advanced to appointment_booked (lifecycle preserved).
    assert session.execute(text("SELECT status FROM leads WHERE id = :l"), {"l": ids["lead"]}).scalar_one() == "appointment_booked"

    # A following NON-lead booking at the same branch/date draws the next token from the same
    # sequence — proving a single canonical allocator shared by both paths.
    second = _book(session, ids, lead_id=None, full_name="Walk-in Patient")["data"]
    assert second["token_number"] == first_token + 1
