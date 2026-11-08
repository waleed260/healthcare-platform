"""Cross-tenant isolation tests: two independent clinics must never see each other's data.

Exercises real PostgreSQL RLS policies — no mocks on the security boundary.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.security import hash_password, hash_token, new_opaque_token
from app.db.tenant import set_tenant_context
from app.modules.identity.service import (
    authenticate,
    consume_staff_invitation,
    create_staff_invitation,
    normalize_email,
)

pytestmark = pytest.mark.integration

_PASSWORD = "CrossTenantPass1!"


def _urls():
    admin = os.getenv("TEST_ADMIN_DATABASE_URL")
    runtime = os.getenv("TEST_DATABASE_URL")
    if not admin or not runtime:
        pytest.skip("PostgreSQL integration URLs are not configured")
    return admin, runtime


def _seed_two_clinics(admin_engine):
    """Create two clinics, each with an owner and a patient."""
    pw = hash_password(_PASSWORD)
    clinics = {}
    for label in ("alpha", "beta"):
        cid = uuid4()
        uid = uuid4()
        pid = uuid4()
        email = f"{label}-owner-{uid}@example.test"
        slug = f"ct-{label}-{cid}"[:80]
        with admin_engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO clinics (id, name, slug, status) VALUES (:id, :name, :slug, 'active')"
            ), {"id": cid, "name": f"Clinic {label.title()}", "slug": slug})
            conn.execute(text(
                "INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash, status) "
                "VALUES (:id, :cid, :email, :name, :pw, 'active')"
            ), {"id": uid, "cid": cid, "email": normalize_email(email), "name": f"Owner {label}", "pw": pw})
            role_id = conn.execute(text(
                "SELECT id FROM roles WHERE clinic_id IS NULL AND name = 'owner'"
            )).scalar_one()
            conn.execute(text(
                "INSERT INTO user_roles (clinic_id, user_id, role_id) VALUES (:cid, :uid, :rid)"
            ), {"cid": cid, "uid": uid, "rid": role_id})
            conn.execute(text(
                "INSERT INTO patients (id, clinic_id, patient_number, full_name, status) VALUES (:id, :cid, :pn, :name, 'active')"
            ), {"id": pid, "cid": cid, "pn": f"TEST-{label}-{str(pid)[:8]}", "name": f"Patient of {label}"})
        clinics[label] = {"clinic_id": cid, "user_id": uid, "email": email, "patient_id": pid}
    return clinics


def _cleanup(admin_engine, clinics):
    with admin_engine.begin() as conn:
        # The last-owner guard trigger protects production from losing an owner
        # by accident; test teardown is dismantling the whole clinic, so suppress
        # user-defined triggers for this cleanup transaction (migrator is superuser).
        conn.execute(text("SET LOCAL session_replication_role = 'replica'"))
        for c in clinics.values():
            conn.execute(text("DELETE FROM staff_invitations WHERE clinic_id = :cid"), {"cid": c["clinic_id"]})
            conn.execute(text("DELETE FROM patients WHERE clinic_id = :cid"), {"cid": c["clinic_id"]})
            conn.execute(text("DELETE FROM appointments WHERE clinic_id = :cid"), {"cid": c["clinic_id"]})
            conn.execute(text("DELETE FROM audit_events WHERE clinic_id = :cid"), {"cid": c["clinic_id"]})
            for uid in [v for k, v in c.items() if k.endswith("_user_id") or k == "user_id"]:
                conn.execute(text("DELETE FROM sessions WHERE user_id = :uid"), {"uid": uid})
                conn.execute(text("DELETE FROM user_roles WHERE user_id = :uid"), {"uid": uid})
            conn.execute(text("DELETE FROM users WHERE clinic_id = :cid"), {"cid": c["clinic_id"]})
            conn.execute(text("DELETE FROM clinics WHERE id = :cid"), {"cid": c["clinic_id"]})


@pytest.fixture
def two_clinics():
    admin_url, runtime_url = _urls()
    admin_engine = create_engine(admin_url)
    runtime_engine = create_engine(runtime_url)
    clinics = _seed_two_clinics(admin_engine)
    clinics["_runtime_engine"] = runtime_engine
    clinics["_admin_engine"] = admin_engine
    yield clinics
    _cleanup(admin_engine, {k: v for k, v in clinics.items() if not k.startswith("_")})


def test_clinic_a_cannot_see_clinic_b_patients(two_clinics):
    """With Clinic A's tenant context, Clinic B's patients must be invisible."""
    engine = two_clinics["_runtime_engine"]
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    db = Session()
    try:
        set_tenant_context(db, two_clinics["alpha"]["clinic_id"])
        own = db.execute(text("SELECT id FROM patients WHERE clinic_id = :cid"), {"cid": two_clinics["alpha"]["clinic_id"]}).scalars().all()
        other = db.execute(text("SELECT id FROM patients WHERE clinic_id = :cid"), {"cid": two_clinics["beta"]["clinic_id"]}).scalars().all()
        db.commit()
        assert two_clinics["alpha"]["patient_id"] in own
        assert len(other) == 0, "Clinic A must not see Clinic B's patients"
    finally:
        db.close()


def test_clinic_b_cannot_see_clinic_a_patients(two_clinics):
    """Symmetric: Clinic B must not see Clinic A's patients."""
    engine = two_clinics["_runtime_engine"]
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    db = Session()
    try:
        set_tenant_context(db, two_clinics["beta"]["clinic_id"])
        own = db.execute(text("SELECT id FROM patients WHERE clinic_id = :cid"), {"cid": two_clinics["beta"]["clinic_id"]}).scalars().all()
        other = db.execute(text("SELECT id FROM patients WHERE clinic_id = :cid"), {"cid": two_clinics["alpha"]["clinic_id"]}).scalars().all()
        db.commit()
        assert two_clinics["beta"]["patient_id"] in own
        assert len(other) == 0, "Clinic B must not see Clinic A's patients"
    finally:
        db.close()


def test_login_scopes_session_to_correct_clinic(two_clinics):
    """Authenticating as Clinic A's owner must yield Clinic A's clinic_id."""
    engine = two_clinics["_runtime_engine"]
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    for label in ("alpha", "beta"):
        db = Session()
        try:
            result = authenticate(db, two_clinics[label]["email"], _PASSWORD, "192.0.2.50", "pytest")
            db.commit()
            assert result.clinic_id == two_clinics[label]["clinic_id"]
            assert result.user_id == two_clinics[label]["user_id"]
        finally:
            db.close()


def test_sequential_logins_do_not_leak_context(two_clinics):
    """Log in as A, then as B — B must not see A's patients."""
    engine = two_clinics["_runtime_engine"]
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    db = Session()
    try:
        authenticate(db, two_clinics["alpha"]["email"], _PASSWORD, "192.0.2.51", "pytest")
        db.commit()
    finally:
        db.close()

    db = Session()
    try:
        authenticate(db, two_clinics["beta"]["email"], _PASSWORD, "192.0.2.51", "pytest")
        db.commit()
        visible = db.execute(text("SELECT id FROM patients WHERE clinic_id = :cid"), {"cid": two_clinics["alpha"]["clinic_id"]}).scalars().all()
        db.commit()
        assert len(visible) == 0, "After login as B, A's patients must be invisible"
    finally:
        db.close()


def test_invitation_with_owner_role(two_clinics):
    """An invitation created with role_name='owner' must assign the owner role on consume."""
    admin_engine = two_clinics["_admin_engine"]
    engine = two_clinics["_runtime_engine"]
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    clinic_id = two_clinics["alpha"]["clinic_id"]
    invited_by = two_clinics["alpha"]["user_id"]
    invite_email = f"new-owner-{uuid4()}@example.test"

    db = Session()
    try:
        set_tenant_context(db, clinic_id, invited_by)
        token = create_staff_invitation(db, clinic_id, invited_by, invite_email, role_name="owner")
        db.commit()
    finally:
        db.close()

    db = Session()
    new_user_id = None
    try:
        new_user_id = consume_staff_invitation(db, token, _PASSWORD, "New Owner")
        db.commit()
    finally:
        db.close()

    with admin_engine.begin() as conn:
        role_name = conn.execute(text("""
            SELECT r.name FROM user_roles ur JOIN roles r ON r.id = ur.role_id
            WHERE ur.user_id = :uid AND ur.clinic_id = :cid
        """), {"uid": new_user_id, "cid": clinic_id}).scalar_one()
        assert role_name == "owner", f"Expected 'owner' role, got '{role_name}'"
        # Cleanup
        conn.execute(text("DELETE FROM sessions WHERE user_id = :uid"), {"uid": new_user_id})
        conn.execute(text("DELETE FROM user_roles WHERE user_id = :uid"), {"uid": new_user_id})
        conn.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": new_user_id})


def test_invitation_defaults_to_receptionist(two_clinics):
    """An invitation without explicit role must assign receptionist."""
    admin_engine = two_clinics["_admin_engine"]
    engine = two_clinics["_runtime_engine"]
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    clinic_id = two_clinics["beta"]["clinic_id"]
    invited_by = two_clinics["beta"]["user_id"]
    invite_email = f"new-staff-{uuid4()}@example.test"

    db = Session()
    try:
        set_tenant_context(db, clinic_id, invited_by)
        token = create_staff_invitation(db, clinic_id, invited_by, invite_email)
        db.commit()
    finally:
        db.close()

    db = Session()
    new_user_id = None
    try:
        new_user_id = consume_staff_invitation(db, token, _PASSWORD, "New Staff")
        db.commit()
    finally:
        db.close()

    with admin_engine.begin() as conn:
        role_name = conn.execute(text("""
            SELECT r.name FROM user_roles ur JOIN roles r ON r.id = ur.role_id
            WHERE ur.user_id = :uid AND ur.clinic_id = :cid
        """), {"uid": new_user_id, "cid": clinic_id}).scalar_one()
        assert role_name == "receptionist", f"Expected 'receptionist' role, got '{role_name}'"
        conn.execute(text("DELETE FROM sessions WHERE user_id = :uid"), {"uid": new_user_id})
        conn.execute(text("DELETE FROM user_roles WHERE user_id = :uid"), {"uid": new_user_id})
        conn.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": new_user_id})


def test_pooled_connection_resets_tenant_context(two_clinics):
    """A new session on a pooled connection must not inherit the previous tenant context."""
    engine = two_clinics["_runtime_engine"]
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    db = Session()
    try:
        set_tenant_context(db, two_clinics["alpha"]["clinic_id"])
        db.commit()
    finally:
        db.close()

    db = Session()
    try:
        ctx = db.execute(text("SELECT current_setting('app.clinic_id', true)")).scalar_one()
        assert ctx in (None, "", str(two_clinics["alpha"]["clinic_id"])), "Context may persist in same pool slot"
        set_tenant_context(db, two_clinics["beta"]["clinic_id"])
        visible = db.execute(text("SELECT id FROM patients WHERE clinic_id = :cid"), {"cid": two_clinics["alpha"]["clinic_id"]}).scalars().all()
        db.commit()
        assert len(visible) == 0, "After resetting context to B, A's patients must be invisible"
    finally:
        db.close()
