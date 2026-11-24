"""Self-service staff access-request flow — integration tests against real RLS.

Covers the security-critical claims: a request grants no access/membership by
itself, duplicates collapse, submission is enumeration-safe, one clinic's
requests are invisible to another (RLS), approval issues an invitation with the
admin-chosen role and records the decision, and the full approve -> accept bridge
creates exactly the approved member. No mocks on the security boundary.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.security import hash_password
from app.db.tenant import set_tenant_context
from app.modules.identity.service import consume_staff_invitation, normalize_email
from app.modules.access_requests.service import (
    AccessRequestError,
    approve_access_request,
    reject_access_request,
    resolve_clinic_id,
    store_access_request,
)

pytestmark = pytest.mark.integration

_PASSWORD = "AccessReqPass1!"


def _urls():
    admin = os.getenv("TEST_ADMIN_DATABASE_URL")
    runtime = os.getenv("TEST_DATABASE_URL")
    if not admin or not runtime:
        pytest.skip("PostgreSQL integration URLs are not configured")
    return admin, runtime


def _seed_two_clinics(admin_engine):
    pw = hash_password(_PASSWORD)
    clinics = {}
    for label in ("alpha", "beta"):
        cid, uid = uuid4(), uuid4()
        email = f"{label}-admin-{uid}@example.test"
        slug = f"ar-{label}-{cid}"[:80]
        with admin_engine.begin() as conn:
            conn.execute(text("INSERT INTO clinics (id, name, slug, status) VALUES (:id, :name, :slug, 'active')"),
                         {"id": cid, "name": f"Clinic {label.title()}", "slug": slug})
            conn.execute(text("INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash, status) "
                              "VALUES (:id, :cid, :email, :name, :pw, 'active')"),
                         {"id": uid, "cid": cid, "email": normalize_email(email), "name": f"Admin {label}", "pw": pw})
            role_id = conn.execute(text("SELECT id FROM roles WHERE clinic_id IS NULL AND name = 'owner'")).scalar_one()
            conn.execute(text("INSERT INTO user_roles (clinic_id, user_id, role_id) VALUES (:cid, :uid, :rid)"),
                         {"cid": cid, "uid": uid, "rid": role_id})
        clinics[label] = {"clinic_id": cid, "admin_id": uid, "admin_email": email, "slug": slug}
    return clinics


def _cleanup(admin_engine, clinics):
    with admin_engine.begin() as conn:
        conn.execute(text("SET LOCAL session_replication_role = 'replica'"))
        for c in clinics.values():
            conn.execute(text("DELETE FROM access_requests WHERE clinic_id = :cid"), {"cid": c["clinic_id"]})
            conn.execute(text("DELETE FROM staff_invitations WHERE clinic_id = :cid"), {"cid": c["clinic_id"]})
            conn.execute(text("DELETE FROM audit_events WHERE clinic_id = :cid"), {"cid": c["clinic_id"]})
            conn.execute(text("DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE clinic_id = :cid)"), {"cid": c["clinic_id"]})
            conn.execute(text("DELETE FROM user_roles WHERE clinic_id = :cid"), {"cid": c["clinic_id"]})
            conn.execute(text("DELETE FROM users WHERE clinic_id = :cid"), {"cid": c["clinic_id"]})
            conn.execute(text("DELETE FROM clinics WHERE id = :cid"), {"cid": c["clinic_id"]})


@pytest.fixture
def clinics():
    admin_url, runtime_url = _urls()
    admin_engine = create_engine(admin_url)
    runtime_engine = create_engine(runtime_url)
    seeded = _seed_two_clinics(admin_engine)
    Session = sessionmaker(bind=runtime_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    seeded["_Session"] = Session
    seeded["_admin_engine"] = admin_engine
    yield seeded
    _cleanup(admin_engine, {k: v for k, v in seeded.items() if not k.startswith("_")})


def _submit(db, clinic_id, email, **kw):
    set_tenant_context(db, clinic_id)
    store_access_request(db, clinic_id, email=email, display_name=kw.get("display_name"),
                         requested_role=kw.get("requested_role"), reason=kw.get("reason"))
    db.commit()


def test_resolve_clinic_id_by_slug(clinics):
    db = clinics["_Session"]()
    try:
        assert resolve_clinic_id(db, clinics["alpha"]["slug"]) == clinics["alpha"]["clinic_id"]
        assert resolve_clinic_id(db, "no-such-clinic-xyz") is None
    finally:
        db.close()


def test_pending_request_creates_no_membership(clinics):
    cid = clinics["alpha"]["clinic_id"]
    email = f"newcomer-{uuid4()}@example.test"
    db = clinics["_Session"]()
    try:
        _submit(db, cid, email)
        set_tenant_context(db, cid)
        rows = db.execute(text("SELECT status FROM access_requests WHERE clinic_id = :c AND normalized_email = :e"),
                          {"c": cid, "e": normalize_email(email)}).scalars().all()
        assert rows == ["pending"]
        db.commit()
    finally:
        db.close()
    # No user / membership was created by the request.
    with clinics["_admin_engine"].begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM users WHERE clinic_id = :c AND normalized_email = :e"),
                            {"c": cid, "e": normalize_email(email)}).scalar_one() == 0


def test_duplicate_pending_requests_collapse(clinics):
    cid = clinics["alpha"]["clinic_id"]
    email = f"dup-{uuid4()}@example.test"
    db = clinics["_Session"]()
    try:
        _submit(db, cid, email)
        _submit(db, cid, email, reason="again")
        set_tenant_context(db, cid)
        count = db.execute(text("SELECT count(*) FROM access_requests WHERE clinic_id = :c AND normalized_email = :e AND status = 'pending'"),
                           {"c": cid, "e": normalize_email(email)}).scalar_one()
        db.commit()
        assert count == 1
    finally:
        db.close()


def test_submit_is_noop_for_existing_active_member(clinics):
    cid = clinics["alpha"]["clinic_id"]
    existing = clinics["alpha"]["admin_email"]  # already an active member
    db = clinics["_Session"]()
    try:
        _submit(db, cid, existing)
        set_tenant_context(db, cid)
        count = db.execute(text("SELECT count(*) FROM access_requests WHERE clinic_id = :c AND normalized_email = :e"),
                           {"c": cid, "e": normalize_email(existing)}).scalar_one()
        db.commit()
        assert count == 0, "An existing member must not create an access request"
    finally:
        db.close()


def test_clinic_a_cannot_see_clinic_b_requests(clinics):
    """RLS: a request stored for Clinic B is invisible under Clinic A's context."""
    email = f"isolated-{uuid4()}@example.test"
    db = clinics["_Session"]()
    try:
        _submit(db, clinics["beta"]["clinic_id"], email)
        # Switch to Clinic A context and confirm B's request is not visible.
        set_tenant_context(db, clinics["alpha"]["clinic_id"])
        visible = db.execute(text("SELECT id FROM access_requests WHERE normalized_email = :e"),
                             {"e": normalize_email(email)}).scalars().all()
        db.commit()
        assert visible == [], "Clinic A must not see Clinic B's access requests"
    finally:
        db.close()


def _pending_id(db, cid, email):
    set_tenant_context(db, cid)
    return db.execute(text("SELECT id FROM access_requests WHERE clinic_id = :c AND normalized_email = :e AND status = 'pending'"),
                      {"c": cid, "e": normalize_email(email)}).scalar_one()


def test_approve_issues_invitation_with_chosen_role_and_marks_request(clinics):
    cid, admin = clinics["alpha"]["clinic_id"], clinics["alpha"]["admin_id"]
    email = f"approve-{uuid4()}@example.test"
    db = clinics["_Session"]()
    try:
        _submit(db, cid, email, requested_role="front desk")
        req_id = _pending_id(db, cid, email)
        set_tenant_context(db, cid, admin)
        token = approve_access_request(db, cid, admin, req_id, role_name="doctor", expected_version=1)
        # Verify within the same transaction: committing resets the (local) tenant
        # context, after which RLS would correctly hide the row.
        row = db.execute(text("SELECT status, invitation_id, decided_by_user_id FROM access_requests WHERE id = :i"), {"i": req_id}).mappings().one()
        assert row["status"] == "approved"
        assert row["invitation_id"] is not None
        assert row["decided_by_user_id"] == admin
        inv = db.execute(text("SELECT intended_role, intended_normalized_email FROM staff_invitations WHERE id = :i"), {"i": row["invitation_id"]}).mappings().one()
        assert inv["intended_role"] == "doctor"
        assert inv["intended_normalized_email"] == normalize_email(email)
        db.commit()
        assert isinstance(token, str) and len(token) >= 32
    finally:
        db.close()


def test_approve_rejects_unknown_role(clinics):
    cid, admin = clinics["alpha"]["clinic_id"], clinics["alpha"]["admin_id"]
    email = f"badrole-{uuid4()}@example.test"
    db = clinics["_Session"]()
    try:
        _submit(db, cid, email)
        req_id = _pending_id(db, cid, email)
        set_tenant_context(db, cid, admin)
        with pytest.raises(AccessRequestError) as exc:
            approve_access_request(db, cid, admin, req_id, role_name="superuser", expected_version=1)
        assert exc.value.http_status == 400
        db.rollback()
    finally:
        db.close()


def test_cannot_decide_an_already_decided_request(clinics):
    cid, admin = clinics["alpha"]["clinic_id"], clinics["alpha"]["admin_id"]
    email = f"twice-{uuid4()}@example.test"
    db = clinics["_Session"]()
    try:
        _submit(db, cid, email)
        req_id = _pending_id(db, cid, email)
        set_tenant_context(db, cid, admin)
        approve_access_request(db, cid, admin, req_id, role_name="receptionist", expected_version=1)
        db.commit()
        set_tenant_context(db, cid, admin)
        with pytest.raises(AccessRequestError) as exc:
            reject_access_request(db, cid, admin, req_id, expected_version=2, note="late")
        assert exc.value.http_status == 409
        db.rollback()
    finally:
        db.close()


def test_reject_grants_no_access(clinics):
    cid, admin = clinics["beta"]["clinic_id"], clinics["beta"]["admin_id"]
    email = f"rejectme-{uuid4()}@example.test"
    db = clinics["_Session"]()
    try:
        _submit(db, cid, email)
        req_id = _pending_id(db, cid, email)
        set_tenant_context(db, cid, admin)
        reject_access_request(db, cid, admin, req_id, expected_version=1, note="not this quarter")
        row = db.execute(text("SELECT status, invitation_id FROM access_requests WHERE id = :i"), {"i": req_id}).mappings().one()
        assert row["status"] == "rejected"
        assert row["invitation_id"] is None
        db.commit()
    finally:
        db.close()
    with clinics["_admin_engine"].begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM users WHERE clinic_id = :c AND normalized_email = :e"),
                            {"c": cid, "e": normalize_email(email)}).scalar_one() == 0
        assert conn.execute(text("SELECT count(*) FROM staff_invitations WHERE clinic_id = :c AND intended_normalized_email = :e"),
                            {"c": cid, "e": normalize_email(email)}).scalar_one() == 0


def test_approve_then_accept_creates_member_with_approved_role(clinics):
    """Full bridge: approve -> consume invitation -> exactly one member with the approved role."""
    cid, admin = clinics["beta"]["clinic_id"], clinics["beta"]["admin_id"]
    email = f"joiner-{uuid4()}@example.test"
    db = clinics["_Session"]()
    new_user_id = None
    try:
        _submit(db, cid, email)
        req_id = _pending_id(db, cid, email)
        set_tenant_context(db, cid, admin)
        token = approve_access_request(db, cid, admin, req_id, role_name="manager", expected_version=1)
        db.commit()
    finally:
        db.close()
    db = clinics["_Session"]()
    try:
        new_user_id = consume_staff_invitation(db, token, _PASSWORD, "Joined Member")
        db.commit()
    finally:
        db.close()
    with clinics["_admin_engine"].begin() as conn:
        role_name = conn.execute(text("SELECT r.name FROM user_roles ur JOIN roles r ON r.id = ur.role_id WHERE ur.user_id = :u AND ur.clinic_id = :c"),
                                 {"u": new_user_id, "c": cid}).scalar_one()
        assert role_name == "manager"
        member_clinic = conn.execute(text("SELECT clinic_id FROM users WHERE id = :u"), {"u": new_user_id}).scalar_one()
        assert member_clinic == cid, "New member must belong only to the approving clinic"
        conn.execute(text("SET LOCAL session_replication_role = 'replica'"))
        conn.execute(text("DELETE FROM sessions WHERE user_id = :u"), {"u": new_user_id})
        conn.execute(text("DELETE FROM user_roles WHERE user_id = :u"), {"u": new_user_id})
        conn.execute(text("DELETE FROM users WHERE id = :u"), {"u": new_user_id})
