"""PostgreSQL evidence that core patient mutations and consent creation are audited.

Regression for remediation M1: ``record_event`` fired for notes, care-team and
consent *revoke* but not for patient create/update/archive or consent *create* —
an asymmetric, compliance-relevant gap. This drives the real routes against the
runtime role and asserts exactly one ``audit_events`` row per action with the
correct ``entity_id`` and no PHI (name, email, DOB, note body) in ``metadata``.

Runs in CI's PostgreSQL service; skipped when integration URLs are unset. All
data is synthetic.
"""
from __future__ import annotations

import json
import os
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.tenant import set_tenant_context
from app.modules.crm import routes
from app.modules.crm.schemas import ConsentCreate, PatientCreate, PatientUpdate

pytestmark = pytest.mark.integration


def _database_urls() -> tuple[str, str]:
    admin_url = os.getenv("TEST_ADMIN_DATABASE_URL")
    runtime_url = os.getenv("TEST_DATABASE_URL")
    if not admin_url or not runtime_url:
        pytest.skip("PostgreSQL integration URLs are not configured")
    return admin_url, runtime_url


def _request() -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())))


def test_patient_lifecycle_and_consent_create_are_audited_without_phi(monkeypatch) -> None:
    admin_url, runtime_url = _database_urls()
    admin = create_engine(admin_url)
    # Match the app engine: ClientCursor renders params as literals so untyped
    # NULLs in the duplicate pre-check (``:email IS NOT NULL``) type-check.
    runtime = create_engine(runtime_url, connect_args={"cursor_factory": psycopg.ClientCursor})
    runtime_session = sessionmaker(bind=runtime, autoflush=False, autocommit=False, expire_on_commit=False)
    clinic_id, user_id = uuid4(), uuid4()
    # Distinctive PHI we must never find echoed back in any audit metadata.
    full_name = f"Synthetic Audit {uuid4().hex[:8]}"
    renamed = f"Synthetic Renamed {uuid4().hex[:8]}"
    email = f"audit-{user_id}@example.test"
    dob = date(1983, 7, 14)

    def _fake_auth(db, *args, **kwargs):
        # Mirror production: establish the transaction-local tenant context that
        # _write_authorized / _authorized would normally set, then skip the
        # session-cookie and CSRF checks that need a real login.
        set_tenant_context(db, clinic_id, user_id)
        return {"clinic_id": clinic_id, "user_id": user_id}

    monkeypatch.setattr(routes, "_write_authorized", _fake_auth)
    monkeypatch.setattr(routes, "_authorized", _fake_auth)

    session = runtime_session()
    try:
        with admin.begin() as connection:
            connection.execute(text("INSERT INTO clinics (id, name, slug) VALUES (:id, 'Synthetic Audit', :slug)"), {"id": clinic_id, "slug": f"audit-{clinic_id}"})
            connection.execute(text("INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash, status) VALUES (:id, :clinic_id, :email, 'Synthetic Audit', 'unused', 'active')"), {"id": user_id, "clinic_id": clinic_id, "email": email})

        created = routes.patient_create(PatientCreate(full_name=full_name, email=email, phone="+15555550123", date_of_birth=dob), _request(), session, "session", "csrf")["data"]
        patient_id = created["id"]
        patient_number = created["patient_number"]

        routes.patient_update(patient_id, PatientUpdate(expected_version=1, full_name=renamed), _request(), session, "session", "csrf")

        consent = routes.consent_create(patient_id, ConsentCreate(consent_type="treatment", status="granted", version="v1"), _request(), session, "session", "csrf")["data"]
        consent_id = consent["id"]

        routes.patient_archive(patient_id, _request(), session, "session", "csrf")

        with runtime.begin() as connection:
            set_tenant_context(connection, clinic_id, user_id)
            rows = connection.execute(text("""
                SELECT action, entity_type, entity_id, metadata
                FROM audit_events
                WHERE clinic_id = :clinic_id
                ORDER BY created_at, action
            """), {"clinic_id": clinic_id}).mappings().all()

        by_action: dict[str, list[dict]] = {}
        for row in rows:
            by_action.setdefault(row["action"], []).append(dict(row))

        # Exactly one row per audited action, each pointing at the right entity.
        for action in ("patient.create", "patient.update", "patient.archive", "consent.create"):
            assert len(by_action.get(action, [])) == 1, f"expected one {action} row, got {by_action.get(action)}"

        assert by_action["patient.create"][0]["entity_id"] == patient_id
        assert by_action["patient.update"][0]["entity_id"] == patient_id
        assert by_action["patient.archive"][0]["entity_id"] == patient_id
        assert by_action["consent.create"][0]["entity_id"] == consent_id

        # Metadata carries only non-PHI keys.
        assert by_action["patient.create"][0]["metadata"] == {"patient_number": patient_number}
        assert by_action["patient.update"][0]["metadata"] == {"fields": ["full_name"]}
        assert by_action["consent.create"][0]["metadata"] == {"consent_type": "treatment", "status": "granted"}

        # No PHI value (name, email, DOB) appears anywhere in any metadata blob.
        all_metadata = json.dumps([row["metadata"] for row in rows], default=str)
        for secret in (full_name, renamed, email, dob.isoformat()):
            assert secret not in all_metadata, f"PHI {secret!r} leaked into audit metadata"
    finally:
        session.close()
        with admin.begin() as connection:
            # audit_events is append-only (a trigger forbids DELETE) and has no FK
            # to clinics, so the synthetic rows are left in place; the unique random
            # clinic_id per run keeps the per-action counts above exact.
            connection.execute(text("DELETE FROM consent_records WHERE clinic_id = :clinic_id"), {"clinic_id": clinic_id})
            connection.execute(text("DELETE FROM patients WHERE clinic_id = :clinic_id"), {"clinic_id": clinic_id})
            connection.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})
            connection.execute(text("DELETE FROM clinics WHERE id = :clinic_id"), {"clinic_id": clinic_id})


def test_date_of_birth_correction_persists_bumps_version_and_is_audited(monkeypatch) -> None:
    """L5: a wrong DOB can be corrected; the change persists, bumps the version,
    and is audited as a patient.update listing date_of_birth (value not logged)."""
    admin_url, runtime_url = _database_urls()
    admin = create_engine(admin_url)
    runtime = create_engine(runtime_url, connect_args={"cursor_factory": psycopg.ClientCursor})
    runtime_session = sessionmaker(bind=runtime, autoflush=False, autocommit=False, expire_on_commit=False)
    clinic_id, user_id = uuid4(), uuid4()
    original_dob = date(1980, 1, 1)
    corrected_dob = date(1980, 12, 31)

    def _fake_auth(db, *args, **kwargs):
        set_tenant_context(db, clinic_id, user_id)
        return {"clinic_id": clinic_id, "user_id": user_id}

    monkeypatch.setattr(routes, "_write_authorized", _fake_auth)
    monkeypatch.setattr(routes, "_authorized", _fake_auth)

    session = runtime_session()
    try:
        with admin.begin() as connection:
            connection.execute(text("INSERT INTO clinics (id, name, slug) VALUES (:id, 'Synthetic DOB', :slug)"), {"id": clinic_id, "slug": f"dob-{clinic_id}"})
            connection.execute(text("INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash, status) VALUES (:id, :clinic_id, :email, 'Synthetic DOB', 'unused', 'active')"), {"id": user_id, "clinic_id": clinic_id, "email": f"dob-{user_id}@example.test"})

        created = routes.patient_create(PatientCreate(full_name="Synthetic DOB", date_of_birth=original_dob), _request(), session, "session", "csrf")["data"]
        patient_id = created["id"]
        assert created["date_of_birth"] == original_dob
        assert created["version"] == 1

        updated = routes.patient_update(patient_id, PatientUpdate(expected_version=1, date_of_birth=corrected_dob), _request(), session, "session", "csrf")["data"]
        assert updated["date_of_birth"] == corrected_dob
        assert updated["version"] == 2

        with runtime.begin() as connection:
            set_tenant_context(connection, clinic_id, user_id)
            persisted = connection.execute(text("SELECT date_of_birth, version FROM patients WHERE clinic_id = :clinic_id AND id = :id"), {"clinic_id": clinic_id, "id": patient_id}).mappings().one()
            assert persisted["date_of_birth"] == corrected_dob
            assert persisted["version"] == 2
            audit = connection.execute(text("SELECT metadata FROM audit_events WHERE clinic_id = :clinic_id AND action = 'patient.update' AND entity_id = :id"), {"clinic_id": clinic_id, "id": patient_id}).mappings().all()
        assert len(audit) == 1
        assert audit[0]["metadata"] == {"fields": ["date_of_birth"]}
        # The DOB value itself is never logged.
        assert corrected_dob.isoformat() not in json.dumps(audit[0]["metadata"], default=str)
    finally:
        session.close()
        with admin.begin() as connection:
            connection.execute(text("DELETE FROM patients WHERE clinic_id = :clinic_id"), {"clinic_id": clinic_id})
            connection.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})
            connection.execute(text("DELETE FROM clinics WHERE id = :clinic_id"), {"clinic_id": clinic_id})
