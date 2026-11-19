"""PART 3.C — the platform clinic-overview endpoint returns non-clinical aggregates only.

Drives the real endpoint with a real platform-admin session against PostgreSQL, and
asserts it reports account/activity counts + modules but never leaks patient records.
"""
import os
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from app.core.security import hash_token, new_opaque_token, utc_now
from app.db.session import SessionLocal
from app.modules.governance import admin_routes

pytestmark = pytest.mark.integration


def _admin_engine():
    url = os.getenv("TEST_ADMIN_DATABASE_URL")
    if not url or not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("PostgreSQL integration URLs are not configured")
    return create_engine(url)


def test_clinic_overview_reports_non_clinical_aggregates() -> None:
    admin = _admin_engine()
    clinic = uuid4()
    platform_user, clinic_user, patient = uuid4(), uuid4(), uuid4()
    token = new_opaque_token()
    now = utc_now()
    try:
        with admin.begin() as c:
            c.execute(text("INSERT INTO clinics (id, name, slug) VALUES (:id, 'Overview Clinic', :slug)"),
                      {"id": clinic, "slug": f"overview-{clinic}"})
            c.execute(text("INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash, status) "
                           "VALUES (:id, :cid, :email, 'Clinic User', 'x', 'active')"),
                      {"id": clinic_user, "cid": clinic, "email": f"cu-{clinic_user}@test.local"})
            c.execute(text("INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash, status, is_platform_admin) "
                           "VALUES (:id, NULL, :email, 'Platform Operator', 'x', 'active', true)"),
                      {"id": platform_user, "email": f"pa-{platform_user}@test.local"})
            c.execute(text("INSERT INTO patients (id, clinic_id, patient_number, full_name) VALUES (:id, :cid, 'OV-1', 'Confidential Patient')"),
                      {"id": patient, "cid": clinic})
            c.execute(text("""INSERT INTO sessions (user_id, token_hash, csrf_token_hash, mfa_verified, ip_hash, idle_expires_at, absolute_expires_at)
                              VALUES (:uid, :th, :ch, true, 'x', :idle, :abs)"""),
                      {"uid": platform_user, "th": hash_token(token), "ch": hash_token("c" * 32),
                       "idle": now + timedelta(hours=1), "abs": now + timedelta(hours=2)})

        db = SessionLocal()
        try:
            request = SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())))
            result = admin_routes.clinic_overview(clinic, request, db, token)
        finally:
            db.close()

        data = result["data"]
        assert data["clinic"]["id"] == clinic
        assert data["clinic"]["name"] == "Overview Clinic"
        assert data["accounts"]["active_users"] == 1
        assert data["accounts"]["total_users"] == 1
        assert data["activity"]["patients_total"] == 1
        assert data["activity"]["appointments_total"] == 0
        assert data["modules"] == []
        # Non-clinical contract: no patient record / name may appear anywhere in the payload.
        assert "Confidential Patient" not in str(result)
    finally:
        with admin.begin() as c:
            c.execute(text("DELETE FROM sessions WHERE user_id = :u"), {"u": platform_user})
            c.execute(text("DELETE FROM patients WHERE clinic_id = :c"), {"c": clinic})
            c.execute(text("DELETE FROM users WHERE id IN (:a, :b)"), {"a": platform_user, "b": clinic_user})
            c.execute(text("DELETE FROM clinics WHERE id = :c"), {"c": clinic})
