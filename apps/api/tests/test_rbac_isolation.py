import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from app.db.tenant import set_tenant_context
from app.modules.authorization.service import has_permission
from app.modules.crm.routes import _patient_scope_sql


pytestmark = pytest.mark.integration


def test_role_permissions_and_branch_scopes_are_tenant_bound() -> None:
    admin_url = os.getenv("TEST_ADMIN_DATABASE_URL")
    runtime_url = os.getenv("TEST_DATABASE_URL")
    if not admin_url or not runtime_url:
        pytest.skip("PostgreSQL integration URLs are not configured")
    admin = create_engine(admin_url)
    runtime = create_engine(runtime_url)
    clinic_id, user_id, branch_a, branch_b = uuid4(), uuid4(), uuid4(), uuid4()
    try:
        with admin.begin() as connection:
            connection.execute(text("INSERT INTO clinics (id, name, slug) VALUES (:id, 'RBAC clinic', :slug)"), {"id": clinic_id, "slug": f"rbac-{clinic_id}"})
            connection.execute(text("INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash) VALUES (:id, :clinic_id, :email, 'Synthetic User', 'not-used')"), {"id": user_id, "clinic_id": clinic_id, "email": f"rbac-{user_id}@example.test"})
            role_id = connection.execute(text("SELECT id FROM roles WHERE name = 'manager' AND clinic_id IS NULL")).scalar_one()
            connection.execute(text("INSERT INTO user_roles (clinic_id, user_id, role_id) VALUES (:clinic_id, :user_id, :role_id)"), {"clinic_id": clinic_id, "user_id": user_id, "role_id": role_id})
            connection.execute(text("INSERT INTO branches (id, clinic_id, code, name) VALUES (:id, :clinic_id, 'A', 'Branch A'), (:id2, :clinic_id, 'B', 'Branch B')"), {"id": branch_a, "id2": branch_b, "clinic_id": clinic_id})
            connection.execute(text("INSERT INTO user_branch_scopes (clinic_id, user_id, branch_id) VALUES (:clinic_id, :user_id, :branch_id)"), {"clinic_id": clinic_id, "user_id": user_id, "branch_id": branch_a})
        with runtime.begin() as connection:
            set_tenant_context(connection, clinic_id, user_id)
            assert has_permission(connection, user_id, clinic_id, "clinic.read")
            assert has_permission(connection, user_id, clinic_id, "clinic.read", branch_a)
            assert not has_permission(connection, user_id, clinic_id, "clinic.read", branch_b)
    finally:
        with admin.begin() as connection:
            connection.execute(text("DELETE FROM user_branch_scopes WHERE clinic_id = :clinic_id"), {"clinic_id": clinic_id})
            connection.execute(text("DELETE FROM user_roles WHERE clinic_id = :clinic_id"), {"clinic_id": clinic_id})
            connection.execute(text("DELETE FROM branches WHERE clinic_id = :clinic_id"), {"clinic_id": clinic_id})
            connection.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})
            connection.execute(text("DELETE FROM clinics WHERE id = :clinic_id"), {"clinic_id": clinic_id})


def test_branch_scoped_crm_visibility_follows_patient_appointments() -> None:
    admin_url = os.getenv("TEST_ADMIN_DATABASE_URL")
    runtime_url = os.getenv("TEST_DATABASE_URL")
    if not admin_url or not runtime_url:
        pytest.skip("PostgreSQL integration URLs are not configured")
    admin = create_engine(admin_url)
    runtime = create_engine(runtime_url)
    clinic_id, user_id, branch_a, branch_b = uuid4(), uuid4(), uuid4(), uuid4()
    patient_a, patient_b, service_id = uuid4(), uuid4(), uuid4()
    try:
        with admin.begin() as connection:
            connection.execute(text("INSERT INTO clinics (id, name, slug) VALUES (:id, 'CRM scope clinic', :slug)"), {"id": clinic_id, "slug": f"crm-scope-{clinic_id}"})
            connection.execute(text("INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash) VALUES (:id, :clinic_id, :email, 'Synthetic Scope User', 'not-used')"), {"id": user_id, "clinic_id": clinic_id, "email": f"crm-scope-{user_id}@example.test"})
            role_id = connection.execute(text("SELECT id FROM roles WHERE name = 'manager' AND clinic_id IS NULL")).scalar_one()
            connection.execute(text("INSERT INTO user_roles (clinic_id, user_id, role_id) VALUES (:clinic_id, :user_id, :role_id)"), {"clinic_id": clinic_id, "user_id": user_id, "role_id": role_id})
            connection.execute(text("INSERT INTO branches (id, clinic_id, code, name) VALUES (:a, :clinic_id, 'A', 'Branch A'), (:b, :clinic_id, 'B', 'Branch B')"), {"a": branch_a, "b": branch_b, "clinic_id": clinic_id})
            connection.execute(text("INSERT INTO user_branch_scopes (clinic_id, user_id, branch_id) VALUES (:clinic_id, :user_id, :branch_id)"), {"clinic_id": clinic_id, "user_id": user_id, "branch_id": branch_a})
            connection.execute(text("INSERT INTO services (id, clinic_id, name, duration_minutes) VALUES (:id, :clinic_id, 'Synthetic consultation', 30)"), {"id": service_id, "clinic_id": clinic_id})
            connection.execute(text("INSERT INTO patients (id, clinic_id, patient_number, full_name) VALUES (:a, :clinic_id, 'SYN-A', 'Synthetic Patient A'), (:b, :clinic_id, 'SYN-B', 'Synthetic Patient B')"), {"a": patient_a, "b": patient_b, "clinic_id": clinic_id})
            connection.execute(text("""
                INSERT INTO appointments (clinic_id, branch_id, service_id, patient_id, starts_at, ends_at, occupancy_start, occupancy_end, reference, idempotency_key, idempotency_body_hash)
                VALUES (:clinic_id, :branch_id, :service_id, :patient_id, '2030-01-01 09:00+00', '2030-01-01 09:30+00', '2030-01-01 09:00+00', '2030-01-01 09:30+00', :reference, :idempotency, repeat('0', 64))
            """), {"clinic_id": clinic_id, "branch_id": branch_a, "service_id": service_id, "patient_id": patient_a, "reference": f"SYN-{clinic_id}-A", "idempotency": f"scope-{clinic_id}-A"})
            connection.execute(text("""
                INSERT INTO appointments (clinic_id, branch_id, service_id, patient_id, starts_at, ends_at, occupancy_start, occupancy_end, reference, idempotency_key, idempotency_body_hash)
                VALUES (:clinic_id, :branch_id, :service_id, :patient_id, '2030-01-01 10:00+00', '2030-01-01 10:30+00', '2030-01-01 10:00+00', '2030-01-01 10:30+00', :reference, :idempotency, repeat('0', 64))
            """), {"clinic_id": clinic_id, "branch_id": branch_b, "service_id": service_id, "patient_id": patient_b, "reference": f"SYN-{clinic_id}-B", "idempotency": f"scope-{clinic_id}-B"})
        with runtime.begin() as connection:
            set_tenant_context(connection, clinic_id, user_id)
            rows = connection.execute(text(f"SELECT p.patient_number FROM patients p WHERE p.clinic_id = :clinic_id AND p.archived_at IS NULL {_patient_scope_sql('p')} ORDER BY p.patient_number"), {"clinic_id": clinic_id, "user_id": user_id}).scalars().all()
            assert rows == ["SYN-A"]
    finally:
        with admin.begin() as connection:
            connection.execute(text("DELETE FROM appointments WHERE clinic_id = :clinic_id"), {"clinic_id": clinic_id})
            connection.execute(text("DELETE FROM patients WHERE clinic_id = :clinic_id"), {"clinic_id": clinic_id})
            connection.execute(text("DELETE FROM services WHERE clinic_id = :clinic_id"), {"clinic_id": clinic_id})
            connection.execute(text("DELETE FROM user_branch_scopes WHERE clinic_id = :clinic_id"), {"clinic_id": clinic_id})
            connection.execute(text("DELETE FROM user_roles WHERE clinic_id = :clinic_id"), {"clinic_id": clinic_id})
            connection.execute(text("DELETE FROM branches WHERE clinic_id = :clinic_id"), {"clinic_id": clinic_id})
            connection.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})
            connection.execute(text("DELETE FROM clinics WHERE id = :clinic_id"), {"clinic_id": clinic_id})
