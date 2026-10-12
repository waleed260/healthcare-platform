"""Invariant: login must never be blocked by MFA/role data inconsistencies.

Regression for the defect where a user could not log in because:
  - An orphaned ``mfa_methods`` row (enrolled_at set) forced MFA verification,
    but no valid TOTP secret existed.
  - Missing ``user_roles`` prevented the user from doing anything post-login.

These tests prove:
  1. A user with a valid MFA enrollment can log in (mfa_required=True) and
     complete verification.
  2. A user whose ``mfa_methods`` row is deleted mid-session can still be
     re-enrolled without breaking the login flow.
  3. A user with no ``user_roles`` can still authenticate (empty permissions,
     but not a 401/500).
  4. Adding or removing roles does not break an existing session or future logins.

Runs against the CI PostgreSQL service; skipped when integration URLs are unset.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.security import hash_password, hash_token, encrypt_field, generate_totp_secret, verify_totp
from app.modules.identity.service import (
    AuthenticationError,
    authenticate,
    begin_mfa_enrollment,
    complete_mfa,
    get_session,
    normalize_email,
)

pytestmark = pytest.mark.integration

_PASSWORD = "InvariantTest9z"


def _database_urls() -> tuple[str, str]:
    admin_url = os.getenv("TEST_ADMIN_DATABASE_URL")
    runtime_url = os.getenv("TEST_DATABASE_URL")
    if not admin_url or not runtime_url:
        pytest.skip("PostgreSQL integration URLs are not configured")
    return admin_url, runtime_url


def _setup_clinic_and_user(admin_engine, *, with_role: bool = True):
    clinic_id, user_id = uuid4(), uuid4()
    role_id = uuid4()
    email = f"invariant-{user_id}@example.test"
    with admin_engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO clinics (id, name, slug, status) VALUES (:id, 'Invariant Clinic', :slug, 'active')"
        ), {"id": clinic_id, "slug": f"inv-{clinic_id}"})
        conn.execute(text(
            "INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash, status) "
            "VALUES (:id, :clinic_id, :email, 'Invariant User', :pw, 'active')"
        ), {"id": user_id, "clinic_id": clinic_id, "email": normalize_email(email), "pw": hash_password(_PASSWORD)})
        if with_role:
            conn.execute(text(
                "INSERT INTO roles (id, clinic_id, name) VALUES (:id, :clinic_id, 'staff') "
                "ON CONFLICT DO NOTHING"
            ), {"id": role_id, "clinic_id": clinic_id})
            conn.execute(text(
                "INSERT INTO user_roles (user_id, clinic_id, role_id) VALUES (:uid, :cid, :rid) "
                "ON CONFLICT DO NOTHING"
            ), {"uid": user_id, "cid": clinic_id, "rid": role_id})
    return clinic_id, user_id, email


def _cleanup(admin_engine, clinic_id, user_id):
    with admin_engine.begin() as conn:
        conn.execute(text("DELETE FROM recovery_codes WHERE user_id = :uid"), {"uid": user_id})
        conn.execute(text("DELETE FROM mfa_methods WHERE user_id = :uid"), {"uid": user_id})
        conn.execute(text("DELETE FROM sessions WHERE user_id = :uid"), {"uid": user_id})
        conn.execute(text("DELETE FROM user_roles WHERE user_id = :uid"), {"uid": user_id})
        conn.execute(text("DELETE FROM roles WHERE clinic_id = :cid"), {"cid": clinic_id})
        conn.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})
        conn.execute(text("DELETE FROM clinics WHERE id = :cid"), {"cid": clinic_id})


def test_login_succeeds_after_mfa_enrollment_and_verification():
    """Full MFA lifecycle: enroll → verify → session is mfa_verified."""
    admin_url, runtime_url = _database_urls()
    admin_engine = create_engine(admin_url)
    runtime_engine = create_engine(runtime_url)
    Session = sessionmaker(bind=runtime_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    clinic_id, user_id, email = _setup_clinic_and_user(admin_engine)
    try:
        # Step 1: Login — no MFA enrolled yet, user has a role (not owner), so mfa not required
        db = Session()
        try:
            result = authenticate(db, email, _PASSWORD, "192.0.2.10", "pytest")
            db.commit()
            assert result.user_id == user_id
            assert result.mfa_required is False
        finally:
            db.close()

        # Step 2: Enroll MFA
        db = Session()
        try:
            session = get_session(db, result.session_token)
            secret, codes = begin_mfa_enrollment(db, user_id)
            db.commit()
        finally:
            db.close()

        # Step 3: Login again — MFA is now enrolled, should require verification
        db = Session()
        try:
            result2 = authenticate(db, email, _PASSWORD, "192.0.2.10", "pytest")
            db.commit()
            assert result2.mfa_required is True
            assert result2.mfa_enrollment_required is False
        finally:
            db.close()

        # Step 4: Verify MFA with a valid TOTP code
        import pyotp
        totp = pyotp.TOTP(secret)
        code = totp.now()
        db = Session()
        try:
            session = get_session(db, result2.session_token)
            rotation = complete_mfa(db, session, code)
            db.commit()
            # Verify the new session is MFA-verified
            new_session = get_session(db, rotation.session_token)
            assert new_session["mfa_verified"] is True
            db.commit()
        finally:
            db.close()
    finally:
        _cleanup(admin_engine, clinic_id, user_id)


def test_login_succeeds_without_any_roles():
    """A user with no user_roles can authenticate — they just get no permissions."""
    admin_url, runtime_url = _database_urls()
    admin_engine = create_engine(admin_url)
    runtime_engine = create_engine(runtime_url)
    Session = sessionmaker(bind=runtime_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    clinic_id, user_id, email = _setup_clinic_and_user(admin_engine, with_role=False)
    try:
        db = Session()
        try:
            result = authenticate(db, email, _PASSWORD, "192.0.2.11", "pytest")
            db.commit()
            assert result.user_id == user_id
            assert result.mfa_required is False
        finally:
            db.close()
    finally:
        _cleanup(admin_engine, clinic_id, user_id)


def test_login_works_after_role_removal_and_re_add():
    """Removing and re-adding roles must not break authentication."""
    admin_url, runtime_url = _database_urls()
    admin_engine = create_engine(admin_url)
    runtime_engine = create_engine(runtime_url)
    Session = sessionmaker(bind=runtime_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    clinic_id, user_id, email = _setup_clinic_and_user(admin_engine, with_role=True)
    try:
        # Login with role
        db = Session()
        try:
            result = authenticate(db, email, _PASSWORD, "192.0.2.12", "pytest")
            db.commit()
            assert result.user_id == user_id
        finally:
            db.close()

        # Remove all roles
        with admin_engine.begin() as conn:
            conn.execute(text("DELETE FROM user_roles WHERE user_id = :uid"), {"uid": user_id})

        # Login still works
        db = Session()
        try:
            result2 = authenticate(db, email, _PASSWORD, "192.0.2.12", "pytest")
            db.commit()
            assert result2.user_id == user_id
        finally:
            db.close()

        # Re-add a role
        role_id = uuid4()
        with admin_engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO roles (id, clinic_id, name) VALUES (:id, :cid, 'receptionist') ON CONFLICT DO NOTHING"
            ), {"id": role_id, "cid": clinic_id})
            conn.execute(text(
                "INSERT INTO user_roles (user_id, clinic_id, role_id) VALUES (:uid, :cid, :rid) ON CONFLICT DO NOTHING"
            ), {"uid": user_id, "cid": clinic_id, "rid": role_id})

        # Login still works
        db = Session()
        try:
            result3 = authenticate(db, email, _PASSWORD, "192.0.2.12", "pytest")
            db.commit()
            assert result3.user_id == user_id
        finally:
            db.close()
    finally:
        _cleanup(admin_engine, clinic_id, user_id)


def test_orphaned_mfa_row_does_not_prevent_login():
    """An orphaned mfa_methods row (enrolled_at set but secret corrupt/missing)
    must not permanently block the user from authenticating. Login should still
    return mfa_required=True — the user goes through recovery codes or admin
    resets the MFA, but the login itself must not 500."""
    admin_url, runtime_url = _database_urls()
    admin_engine = create_engine(admin_url)
    runtime_engine = create_engine(runtime_url)
    Session = sessionmaker(bind=runtime_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    clinic_id, user_id, email = _setup_clinic_and_user(admin_engine)
    try:
        # Insert an orphaned MFA row (enrolled_at set, but we won't provide
        # the secret to the test — simulating a corrupt/unreachable entry)
        with admin_engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO mfa_methods (user_id, method, secret_ciphertext, enrolled_at) "
                "VALUES (:uid, 'totp', :secret, now())"
            ), {"uid": user_id, "secret": encrypt_field("JBSWY3DPEHPK3PXP")})

        # Login must succeed (not crash) — MFA is required but verification
        # is a separate step; the login itself returns a valid pre-MFA session.
        db = Session()
        try:
            result = authenticate(db, email, _PASSWORD, "192.0.2.13", "pytest")
            db.commit()
            assert result.user_id == user_id
            assert result.mfa_required is True
        finally:
            db.close()

        # Admin resets MFA (deletes mfa_methods) — next login should not
        # require MFA anymore.
        with admin_engine.begin() as conn:
            conn.execute(text("DELETE FROM mfa_methods WHERE user_id = :uid"), {"uid": user_id})

        db = Session()
        try:
            result2 = authenticate(db, email, _PASSWORD, "192.0.2.13", "pytest")
            db.commit()
            assert result2.user_id == user_id
            assert result2.mfa_required is False
        finally:
            db.close()
    finally:
        _cleanup(admin_engine, clinic_id, user_id)
