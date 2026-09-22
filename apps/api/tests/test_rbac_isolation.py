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


def test_database_preserves_one_active_clinic_owner() -> None:
    admin_url = os.getenv("TEST_ADMIN_DATABASE_URL")
    if not admin_url:
        pytest.skip("PostgreSQL integration URL is not configured")
    admin = create_engine(admin_url)
    clinic_id, owner_a, owner_b = uuid4(), uuid4(), uuid4()
    with admin.connect() as connection:
        outer = connection.begin()
        connection.execute(text("INSERT INTO clinics (id, name, slug) VALUES (:id, 'Owner guard clinic', :slug)"), {"id": clinic_id, "slug": f"owner-guard-{clinic_id}"})
        connection.execute(text("""
            INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash)
            VALUES (:owner_a, :clinic_id, :email_a, 'Synthetic Owner A', 'not-used'),
                   (:owner_b, :clinic_id, :email_b, 'Synthetic Owner B', 'not-used')
        """), {"owner_a": owner_a, "owner_b": owner_b, "clinic_id": clinic_id, "email_a": f"owner-a-{owner_a}@example.test", "email_b": f"owner-b-{owner_b}@example.test"})
        role_id = connection.execute(text("SELECT id FROM roles WHERE name = 'owner' AND clinic_id IS NULL")).scalar_one()
        connection.execute(text("INSERT INTO user_roles (clinic_id, user_id, role_id) VALUES (:clinic_id, :owner_a, :role_id), (:clinic_id, :owner_b, :role_id)"), {"clinic_id": clinic_id, "owner_a": owner_a, "owner_b": owner_b, "role_id": role_id})
        connection.execute(text("DELETE FROM user_roles WHERE clinic_id = :clinic_id AND user_id = :owner_a AND role_id = :role_id"), {"clinic_id": clinic_id, "owner_a": owner_a, "role_id": role_id})
        savepoint = connection.begin_nested()
        with pytest.raises(Exception, match="final active clinic owner"):
            connection.execute(text("DELETE FROM user_roles WHERE clinic_id = :clinic_id AND user_id = :owner_b AND role_id = :role_id"), {"clinic_id": clinic_id, "owner_b": owner_b, "role_id": role_id})
        savepoint.rollback()
        savepoint = connection.begin_nested()
        with pytest.raises(Exception, match="final active clinic owner"):
            connection.execute(text("UPDATE users SET status = 'suspended' WHERE id = :owner_b"), {"owner_b": owner_b})
        savepoint.rollback()
        outer.rollback()


def test_platform_support_context_grants_only_recorded_permissions() -> None:
    admin_url = os.getenv("TEST_ADMIN_DATABASE_URL")
    runtime_url = os.getenv("TEST_DATABASE_URL")
    if not admin_url or not runtime_url:
        pytest.skip("PostgreSQL integration URLs are not configured")
    admin = create_engine(admin_url)
    runtime = create_engine(runtime_url)
    clinic_id, requester_id, approver_id, platform_id, access_id = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    with admin.connect() as connection:
        outer = connection.begin()
        connection.execute(text("INSERT INTO clinics (id, name, slug) VALUES (:id, 'Support context clinic', :slug)"), {"id": clinic_id, "slug": f"support-context-{clinic_id}"})
        connection.execute(text("""
            INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash, is_platform_admin)
            VALUES (:requester, :clinic_id, :requester_email, 'Synthetic Requester', 'not-used', false),
                   (:approver, :clinic_id, :approver_email, 'Synthetic Approver', 'not-used', false),
                   (:platform, NULL, :platform_email, 'Synthetic Platform Admin', 'not-used', true)
        """), {"requester": requester_id, "approver": approver_id, "platform": platform_id, "clinic_id": clinic_id, "requester_email": f"support-requester-{requester_id}@example.test", "approver_email": f"support-approver-{approver_id}@example.test", "platform_email": f"support-platform-{platform_id}@example.test"})
        connection.execute(text("""
            INSERT INTO support_access_sessions (id, clinic_id, requested_by_user_id, approved_by_user_id, reason, permissions, expires_at)
            VALUES (:access_id, :clinic_id, :requester, :approver, 'Synthetic support investigation', '["patient.read"]'::jsonb, now() + interval '30 minutes')
        """), {"access_id": access_id, "clinic_id": clinic_id, "requester": requester_id, "approver": approver_id})
        savepoint = connection.begin_nested()
        with pytest.raises(Exception, match="platform administrator"):
            connection.execute(text("""
                INSERT INTO sessions (user_id, support_access_id, token_hash, csrf_token_hash, ip_hash, idle_expires_at, absolute_expires_at)
                VALUES (:user_id, :access_id, repeat('a', 64), repeat('b', 64), repeat('c', 64), now() + interval '1 hour', now() + interval '1 day')
            """), {"user_id": requester_id, "access_id": access_id})
        savepoint.rollback()
        outer.commit()
    try:
        with runtime.begin() as connection:
            set_tenant_context(connection, clinic_id, platform_id)
            connection.execute(text("SELECT set_config('app.support_access_id', :access_id, true)"), {"access_id": str(access_id)})
            assert has_permission(connection, platform_id, clinic_id, "patient.read")
            assert not has_permission(connection, platform_id, clinic_id, "patient.document.read")
    finally:
        with admin.begin() as connection:
            connection.execute(text("DELETE FROM support_access_sessions WHERE id = :access_id"), {"access_id": access_id})
            connection.execute(text("DELETE FROM users WHERE id IN (:requester, :approver, :platform)"), {"requester": requester_id, "approver": approver_id, "platform": platform_id})
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
