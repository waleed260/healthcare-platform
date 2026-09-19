"""PostgreSQL evidence for CRM-008 care-team and tenant isolation behavior.

This runs in CI's PostgreSQL service. It is intentionally skipped only when a
developer has not configured local integration URLs; no patient data is used.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from app.db.tenant import set_tenant_context
from app.modules.crm.routes import _patient_scope_sql


pytestmark = pytest.mark.integration


def _database_urls() -> tuple[str, str]:
    admin_url = os.getenv("TEST_ADMIN_DATABASE_URL")
    runtime_url = os.getenv("TEST_DATABASE_URL")
    if not admin_url or not runtime_url:
        pytest.skip("PostgreSQL integration URLs are not configured")
    return admin_url, runtime_url


def test_care_team_grants_only_its_doctor_patient_scope_and_rls_isolates_membership() -> None:
    admin_url, runtime_url = _database_urls()
    admin = create_engine(admin_url)
    runtime = create_engine(runtime_url)
    clinic_a, clinic_b, doctor_user, doctor_profile = uuid4(), uuid4(), uuid4(), uuid4()
    patient_a, patient_a_unassigned, patient_b = uuid4(), uuid4(), uuid4()
    try:
        with admin.begin() as connection:
            connection.execute(text("""
                INSERT INTO clinics (id, name, slug) VALUES
                  (:clinic_a, 'Synthetic care team A', :slug_a),
                  (:clinic_b, 'Synthetic care team B', :slug_b)
            """), {"clinic_a": clinic_a, "clinic_b": clinic_b, "slug_a": f"care-team-a-{clinic_a}", "slug_b": f"care-team-b-{clinic_b}"})
            connection.execute(text("""
                INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash)
                VALUES (:id, :clinic_id, :email, 'Synthetic care doctor', 'not-used')
            """), {"id": doctor_user, "clinic_id": clinic_a, "email": f"care-doctor-{doctor_user}@example.test"})
            doctor_role = connection.execute(text("SELECT id FROM roles WHERE name = 'doctor' AND clinic_id IS NULL")).scalar_one()
            connection.execute(text("INSERT INTO user_roles (clinic_id, user_id, role_id) VALUES (:clinic_id, :user_id, :role_id)"), {"clinic_id": clinic_a, "user_id": doctor_user, "role_id": doctor_role})
            connection.execute(text("""
                INSERT INTO doctor_profiles (id, clinic_id, user_id, public_name)
                VALUES (:id, :clinic_id, :user_id, 'Synthetic Care Doctor')
            """), {"id": doctor_profile, "clinic_id": clinic_a, "user_id": doctor_user})
            connection.execute(text("""
                INSERT INTO patients (id, clinic_id, patient_number, full_name) VALUES
                  (:patient_a, :clinic_a, 'CARE-A', 'Synthetic Assigned'),
                  (:patient_a_unassigned, :clinic_a, 'CARE-NO', 'Synthetic Unassigned'),
                  (:patient_b, :clinic_b, 'CARE-B', 'Synthetic Other Tenant')
            """), {"patient_a": patient_a, "patient_a_unassigned": patient_a_unassigned, "patient_b": patient_b, "clinic_a": clinic_a, "clinic_b": clinic_b})
            connection.execute(text("""
                INSERT INTO patient_care_team (clinic_id, patient_id, doctor_id, assigned_by_user_id)
                VALUES (:clinic_id, :patient_id, :doctor_id, :assigned_by)
            """), {"clinic_id": clinic_a, "patient_id": patient_a, "doctor_id": doctor_profile, "assigned_by": doctor_user})
        with runtime.begin() as connection:
            set_tenant_context(connection, clinic_a, doctor_user)
            visible_patients = connection.execute(text(f"""
                SELECT patient_number FROM patients p
                WHERE p.clinic_id = :clinic_id AND p.archived_at IS NULL
                {_patient_scope_sql('p')}
                ORDER BY patient_number
            """), {"clinic_id": clinic_a, "user_id": doctor_user}).scalars().all()
            assert visible_patients == ["CARE-A"]
            memberships = connection.execute(text("SELECT patient_id FROM patient_care_team ORDER BY patient_id")).scalars().all()
            assert memberships == [patient_a]
            with pytest.raises(Exception):
                with connection.begin_nested():
                    connection.execute(text("""
                        INSERT INTO patient_care_team (clinic_id, patient_id, doctor_id, assigned_by_user_id)
                        VALUES (:clinic_id, :patient_id, :doctor_id, :assigned_by)
                    """), {"clinic_id": clinic_b, "patient_id": patient_b, "doctor_id": doctor_profile, "assigned_by": doctor_user})
    finally:
        with admin.begin() as connection:
            connection.execute(text("DELETE FROM patient_care_team WHERE clinic_id IN (:clinic_a, :clinic_b)"), {"clinic_a": clinic_a, "clinic_b": clinic_b})
            connection.execute(text("DELETE FROM patients WHERE clinic_id IN (:clinic_a, :clinic_b)"), {"clinic_a": clinic_a, "clinic_b": clinic_b})
            connection.execute(text("DELETE FROM doctor_profiles WHERE clinic_id = :clinic_id"), {"clinic_id": clinic_a})
            connection.execute(text("DELETE FROM user_roles WHERE clinic_id = :clinic_id"), {"clinic_id": clinic_a})
            connection.execute(text("DELETE FROM users WHERE id = :id"), {"id": doctor_user})
            connection.execute(text("DELETE FROM clinics WHERE id IN (:clinic_a, :clinic_b)"), {"clinic_a": clinic_a, "clinic_b": clinic_b})
