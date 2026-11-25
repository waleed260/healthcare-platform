"""Regression evidence for the rebuilt Leads lifecycle (docs/LEADS_IMPLEMENTATION_PLAN.md).

Schema-level tests prove the manual API refuses event-only stages (D2 fix at the contract edge).
Integration tests run against real PostgreSQL RLS and exercise the event-driven lead service
(booking link D1, attendance->visited, cancel/no-show revert + follow-up D5) and the shared,
safe patient resolver (D4). They auto-skip without the two integration DB URLs.
"""
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, text

from app.db.tenant import set_tenant_context
from app.modules.blueprint_core.lead_service import (
    create_lead_follow_up,
    link_appointment_to_lead,
    mark_lead_visited,
    revert_lead_if_no_active_appointment,
)
from app.modules.blueprint_core.schemas import LeadFollowUpUpdate, LeadUpdate
from app.modules.crm.identity import DuplicatePatientReview, resolve_patient


# --- Schema contract (no DB) ---------------------------------------------------------------

def test_manual_lead_update_rejects_event_only_stages() -> None:
    """Booking / visit / conversion are backend events, never a manual dropdown move (D2)."""
    for blocked in ("appointment_booked", "visited", "converted"):
        with pytest.raises(ValidationError):
            LeadUpdate(expected_version=1, status=blocked)
    assert LeadUpdate(expected_version=1, status="contacted").status == "contacted"


def test_follow_up_update_only_allows_terminal_actions() -> None:
    assert LeadFollowUpUpdate(expected_version=1, status="completed").status == "completed"
    with pytest.raises(ValidationError):
        LeadFollowUpUpdate(expected_version=1, status="pending")


# --- Integration harness -------------------------------------------------------------------

pytestmark_integration = pytest.mark.integration


def _engines():
    admin_url = os.getenv("TEST_ADMIN_DATABASE_URL")
    runtime_url = os.getenv("TEST_DATABASE_URL")
    if not admin_url or not runtime_url:
        pytest.skip("PostgreSQL integration URLs are not configured")
    # ClientCursor so untyped NULL email/phone params bind cleanly (see memory test-db-setup).
    return (
        create_engine(admin_url),
        create_engine(runtime_url, connect_args={"cursor_factory": psycopg.ClientCursor}),
    )


def _seed_clinic(connection, clinic_id, user_id):
    connection.execute(text(
        "INSERT INTO clinics (id, name, slug) VALUES (:c, 'Synthetic lead clinic', :slug)"
    ), {"c": clinic_id, "slug": f"lead-lifecycle-{clinic_id}"})
    connection.execute(text(
        "INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash) "
        "VALUES (:u, :c, :email, 'Synthetic staff', 'unused')"
    ), {"u": user_id, "c": clinic_id, "email": f"lead-{user_id}@example.test"})


def _cleanup(admin, clinic_id):
    with admin.begin() as c:
        for table in ("appointments", "lead_follow_ups", "lead_stage_history", "lead_activities", "leads",
                      "patients", "services", "user_branch_scopes", "user_specialty_scopes", "branches",
                      "users", "clinics"):
            key = "id" if table == "clinics" else "clinic_id"
            c.execute(text(f"DELETE FROM {table} WHERE {key} = :c"), {"c": clinic_id})


@pytestmark_integration
def test_booking_link_and_attendance_and_no_auto_convert():
    admin, runtime = _engines()
    clinic_id, user_id, lead_id = uuid4(), uuid4(), uuid4()
    try:
        with admin.begin() as c:
            _seed_clinic(c, clinic_id, user_id)
            c.execute(text(
                "INSERT INTO leads (id, clinic_id, full_name, source, status) "
                "VALUES (:l, :c, 'Prospect', 'call', 'qualified')"
            ), {"l": lead_id, "c": clinic_id})
        with runtime.begin() as c:
            set_tenant_context(c, clinic_id, user_id)
            # D1: booking advances a qualified lead to appointment_booked and records history.
            assert link_appointment_to_lead(c, clinic_id, lead_id, user_id) is True
            assert c.execute(text("SELECT status FROM leads WHERE id = :l"), {"l": lead_id}).scalar_one() == "appointment_booked"
            # Idempotent: a second linked appointment does not regress or duplicate the stage.
            assert link_appointment_to_lead(c, clinic_id, lead_id, user_id) is False
            # Attendance is the authoritative visit; it fires exactly once.
            assert mark_lead_visited(c, clinic_id, lead_id, user_id) is True
            assert mark_lead_visited(c, clinic_id, lead_id, user_id) is False
            assert c.execute(text("SELECT status FROM leads WHERE id = :l"), {"l": lead_id}).scalar_one() == "visited"
            # D2: reaching visited never auto-associates a patient.
            assert c.execute(text("SELECT converted_to_patient_id FROM leads WHERE id = :l"), {"l": lead_id}).scalar_one() is None
            # Both events were recorded (same-transaction rows share now(), so compare as a set).
            stages = c.execute(text(
                "SELECT to_status FROM lead_stage_history WHERE lead_id = :l"
            ), {"l": lead_id}).scalars().all()
            assert set(stages) == {"appointment_booked", "visited"}
    finally:
        _cleanup(admin, clinic_id)
        admin.dispose(); runtime.dispose()


@pytestmark_integration
def test_cancellation_reverts_lead_and_creates_follow_up_not_lost():
    admin, runtime = _engines()
    clinic_id, user_id, lead_id = uuid4(), uuid4(), uuid4()
    try:
        with admin.begin() as c:
            _seed_clinic(c, clinic_id, user_id)
            c.execute(text(
                "INSERT INTO leads (id, clinic_id, full_name, source, status, assigned_to_user_id) "
                "VALUES (:l, :c, 'Prospect', 'call', 'appointment_booked', :u)"
            ), {"l": lead_id, "c": clinic_id, "u": user_id})
        with runtime.begin() as c:
            set_tenant_context(c, clinic_id, user_id)
            # No active appointment remains -> back to qualified (never lost, never visited) + follow-up.
            assert revert_lead_if_no_active_appointment(c, clinic_id, lead_id, user_id, "appointment cancelled") is True
            assert c.execute(text("SELECT status FROM leads WHERE id = :l"), {"l": lead_id}).scalar_one() == "qualified"
            fu = c.execute(text(
                "SELECT description, status, assigned_to_user_id FROM lead_follow_ups WHERE lead_id = :l"
            ), {"l": lead_id}).mappings().one()
            assert fu["status"] == "pending" and fu["assigned_to_user_id"] == user_id
            assert "cancelled" in fu["description"]
    finally:
        _cleanup(admin, clinic_id)
        admin.dispose(); runtime.dispose()


@pytestmark_integration
def test_revert_is_noop_while_an_active_appointment_remains():
    admin, runtime = _engines()
    clinic_id, user_id, lead_id = uuid4(), uuid4(), uuid4()
    branch_id, service_id, patient_id, appt_id = uuid4(), uuid4(), uuid4(), uuid4()
    now = datetime.now(timezone.utc)
    try:
        with admin.begin() as c:
            _seed_clinic(c, clinic_id, user_id)
            c.execute(text("INSERT INTO leads (id, clinic_id, full_name, source, status) VALUES (:l, :c, 'Prospect', 'call', 'appointment_booked')"), {"l": lead_id, "c": clinic_id})
            c.execute(text("INSERT INTO branches (clinic_id, code, name) VALUES (:c, 'B1', 'Branch 1')"), {"c": clinic_id})
            branch_id = c.execute(text("SELECT id FROM branches WHERE clinic_id = :c"), {"c": clinic_id}).scalar_one()
            c.execute(text("INSERT INTO services (id, clinic_id, name, duration_minutes) VALUES (:s, :c, 'Consult', 30)"), {"s": service_id, "c": clinic_id})
            c.execute(text("INSERT INTO patients (id, clinic_id, patient_number, full_name) VALUES (:p, :c, 'P-TEST', 'Pat')"), {"p": patient_id, "c": clinic_id})
            c.execute(text("""
                INSERT INTO appointments (id, clinic_id, branch_id, service_id, patient_id, lead_id, status,
                    starts_at, ends_at, occupancy_start, occupancy_end, reference, idempotency_key, idempotency_body_hash)
                VALUES (:a, :c, :b, :s, :p, :l, 'confirmed', :t0, :t1, :t0, :t1, 'BK-T', :k, 'h')
            """), {"a": appt_id, "c": clinic_id, "b": branch_id, "s": service_id, "p": patient_id, "l": lead_id,
                   "t0": now + timedelta(days=1), "t1": now + timedelta(days=1, minutes=30), "k": f"k-{appt_id}"})
        with runtime.begin() as c:
            set_tenant_context(c, clinic_id, user_id)
            # A second appointment is still active, so the lead stays booked and no follow-up is queued.
            assert revert_lead_if_no_active_appointment(c, clinic_id, lead_id, user_id, "one of two cancelled") is False
            assert c.execute(text("SELECT status FROM leads WHERE id = :l"), {"l": lead_id}).scalar_one() == "appointment_booked"
            assert c.execute(text("SELECT count(*) FROM lead_follow_ups WHERE lead_id = :l"), {"l": lead_id}).scalar_one() == 0
    finally:
        _cleanup(admin, clinic_id)
        admin.dispose(); runtime.dispose()


@pytestmark_integration
def test_shared_resolver_single_conflict_and_excludes_archived():
    admin, runtime = _engines()
    clinic_id, user_id = uuid4(), uuid4()
    pa, pb, pc = uuid4(), uuid4(), uuid4()
    try:
        with admin.begin() as c:
            _seed_clinic(c, clinic_id, user_id)
            c.execute(text("INSERT INTO patients (id, clinic_id, patient_number, full_name, normalized_email, normalized_phone) VALUES (:p, :c, 'P-A', 'A', 'a@x.test', '111111111')"), {"p": pa, "c": clinic_id})
            c.execute(text("INSERT INTO patients (id, clinic_id, patient_number, full_name, normalized_phone) VALUES (:p, :c, 'P-B', 'B', '222222222')"), {"p": pb, "c": clinic_id})
            # An archived record that would match by email must never be selected.
            c.execute(text("INSERT INTO patients (id, clinic_id, patient_number, full_name, normalized_email, archived_at) VALUES (:p, :c, 'P-C', 'C', 'ghost@x.test', now())"), {"p": pc, "c": clinic_id})
        with runtime.begin() as c:
            set_tenant_context(c, clinic_id, user_id)
            # Single unambiguous match -> reuse it.
            assert resolve_patient(c, clinic_id, full_name="A", email="a@x.test", phone=None, patient_number="P-NEW1", interactive=True) == pa
            # Conflict: email -> A, phone -> B. Interactive must defer to a human (D4).
            with pytest.raises(DuplicatePatientReview) as review:
                resolve_patient(c, clinic_id, full_name="?", email="a@x.test", phone="222222222", patient_number="P-NEW2", interactive=True)
            assert set(review.value.candidates) == {pa, pb}
            # Same conflict, non-interactive (public): create a fresh patient, never guess.
            created = resolve_patient(c, clinic_id, full_name="Web", email="a@x.test", phone="222222222", patient_number="P-NEW3", interactive=False)
            assert created not in (pa, pb, pc)
            # Archived/merged records are never matched -> a new patient is created.
            fresh = resolve_patient(c, clinic_id, full_name="Ghostbuster", email="ghost@x.test", phone=None, patient_number="P-NEW4", interactive=True)
            assert fresh != pc
    finally:
        _cleanup(admin, clinic_id)
        admin.dispose(); runtime.dispose()


@pytestmark_integration
def test_new_tables_are_tenant_isolated():
    admin, runtime = _engines()
    clinic_a, clinic_b, user_a, lead_b = uuid4(), uuid4(), uuid4(), uuid4()
    try:
        with admin.begin() as c:
            _seed_clinic(c, clinic_a, user_a)
            c.execute(text("INSERT INTO clinics (id, name, slug) VALUES (:c, 'Other', :slug)"), {"c": clinic_b, "slug": f"other-{clinic_b}"})
            c.execute(text("INSERT INTO leads (id, clinic_id, full_name, source) VALUES (:l, :c, 'B', 'call')"), {"l": lead_b, "c": clinic_b})
            c.execute(text("INSERT INTO lead_stage_history (clinic_id, lead_id, to_status) VALUES (:c, :l, 'new')"), {"c": clinic_b, "l": lead_b})
        with runtime.begin() as c:
            set_tenant_context(c, clinic_a, user_a)
            # Clinic A sees none of clinic B's stage history despite no explicit clinic filter (RLS).
            assert c.execute(text("SELECT count(*) FROM lead_stage_history")).scalar_one() == 0
            assert c.execute(text("SELECT count(*) FROM lead_follow_ups")).scalar_one() == 0
    finally:
        _cleanup(admin, clinic_a)
        _cleanup(admin, clinic_b)
        admin.dispose(); runtime.dispose()


@pytestmark_integration
def test_booking_rejects_a_lead_outside_the_users_scope(monkeypatch):
    """A branch-scoped user cannot attach an appointment to a lead outside their scope by
    supplying its id (intra-tenant object-level authorization). The in-scope lead passes the
    gate and only fails later for an unrelated, non-security reason."""
    from app.modules.appointments import routes as appointment_routes
    from app.modules.appointments.schemas import InternalBookingRequest

    admin, runtime = _engines()
    clinic_id, user_id, lead_in, lead_out = uuid4(), uuid4(), uuid4(), uuid4()
    try:
        with admin.begin() as c:
            _seed_clinic(c, clinic_id, user_id)
            c.execute(text("INSERT INTO branches (clinic_id, code, name) VALUES (:c, 'SCOPE-A', 'Branch A')"), {"c": clinic_id})
            c.execute(text("INSERT INTO branches (clinic_id, code, name) VALUES (:c, 'SCOPE-B', 'Branch B')"), {"c": clinic_id})
            branch_a = c.execute(text("SELECT id FROM branches WHERE clinic_id = :c AND code = 'SCOPE-A'"), {"c": clinic_id}).scalar_one()
            branch_b = c.execute(text("SELECT id FROM branches WHERE clinic_id = :c AND code = 'SCOPE-B'"), {"c": clinic_id}).scalar_one()
            c.execute(text("INSERT INTO user_branch_scopes (clinic_id, user_id, branch_id) VALUES (:c, :u, :b)"), {"c": clinic_id, "u": user_id, "b": branch_a})
            c.execute(text("INSERT INTO leads (id, clinic_id, full_name, source, status, branch_id) VALUES (:l, :c, 'In', 'call', 'qualified', :b)"), {"l": lead_in, "c": clinic_id, "b": branch_a})
            c.execute(text("INSERT INTO leads (id, clinic_id, full_name, source, status, branch_id) VALUES (:l, :c, 'Out', 'call', 'qualified', :b)"), {"l": lead_out, "c": clinic_id, "b": branch_b})

        # Auth/CSRF stubbed; the real set_tenant_context runs so _require_lead evaluates under RLS.
        monkeypatch.setattr(appointment_routes, "_staff_authorized", lambda db, token, permission, branch_id=None: (set_tenant_context(db, clinic_id, user_id), {"clinic_id": clinic_id, "user_id": user_id})[1])
        monkeypatch.setattr(appointment_routes, "_csrf", lambda *a, **k: None)
        req = SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())))

        def book(conn, lead_id):
            payload = InternalBookingRequest(branch_id=branch_a, service_id=uuid4(),
                                             starts_at=datetime.now(timezone.utc) + timedelta(days=1),
                                             patient_id=uuid4(), lead_id=lead_id)
            return appointment_routes.create_internal_booking(payload, req, db=conn, session_token="x", csrf_token="x", idempotency_key=f"idem-{uuid4()}")

        with runtime.connect() as conn:
            # Out-of-scope lead: blocked at the lead gate with "Lead not found".
            with pytest.raises(HTTPException) as blocked:
                book(conn, lead_out)
            assert blocked.value.detail["error"]["message"] == "Lead not found."
            conn.rollback()
            # In-scope lead: passes the gate, then fails for an unrelated reason (no branch/service seeded).
            with pytest.raises(HTTPException) as passed_gate:
                book(conn, lead_in)
            assert "branch or service" in passed_gate.value.detail["error"]["message"]
            conn.rollback()
    finally:
        _cleanup(admin, clinic_id)
        admin.dispose(); runtime.dispose()
