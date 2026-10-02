"""PostgreSQL evidence for blueprint §9.1 lead history isolation and immutability."""

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.db.tenant import set_tenant_context
from app.modules.blueprint_core.routes import _require_activity_lead


pytestmark = pytest.mark.integration


def test_lead_activity_rls_relationships_and_immutable_runtime_history():
    admin_url = os.getenv("TEST_ADMIN_DATABASE_URL")
    runtime_url = os.getenv("TEST_DATABASE_URL")
    if not admin_url or not runtime_url:
        pytest.skip("PostgreSQL integration URLs are not configured")
    admin, runtime = create_engine(admin_url), create_engine(runtime_url)
    clinic_a, clinic_b, user_a, user_b, lead_a, lead_b = [uuid4() for _ in range(6)]
    values = {
        "clinic_a": clinic_a, "clinic_b": clinic_b, "user_a": user_a, "user_b": user_b,
        "lead_a": lead_a, "lead_b": lead_b,
        "slug_a": f"activity-a-{clinic_a}", "slug_b": f"activity-b-{clinic_b}",
        "email_a": f"activity-{user_a}@example.test",
        "email_b": f"activity-{user_b}@example.test",
    }
    try:
        with admin.begin() as connection:
            connection.execute(text("""
                INSERT INTO clinics (id, name, slug) VALUES
                    (:clinic_a, 'Synthetic activity A', :slug_a),
                    (:clinic_b, 'Synthetic activity B', :slug_b)
            """), values)
            connection.execute(text("""
                INSERT INTO users
                    (id, clinic_id, normalized_email, display_name, password_hash) VALUES
                    (:user_a, :clinic_a, :email_a, 'Synthetic A', 'unused'),
                    (:user_b, :clinic_b, :email_b, 'Synthetic B', 'unused')
            """), values)
            connection.execute(text("""
                INSERT INTO leads (id, clinic_id, full_name, source) VALUES
                    (:lead_a, :clinic_a, 'Synthetic prospect A', 'call'),
                    (:lead_b, :clinic_b, 'Synthetic prospect B', 'website')
            """), values)
            connection.execute(text("""
                INSERT INTO lead_activities (clinic_id, lead_id, actor_user_id, kind, body)
                VALUES (:clinic_a, :lead_a, :user_a, 'note', 'Synthetic A note'),
                       (:clinic_b, :lead_b, :user_b, 'note', 'Synthetic B note')
            """), values)
            rls = connection.execute(text("""
                SELECT relrowsecurity, relforcerowsecurity FROM pg_class
                WHERE oid = 'lead_activities'::regclass
            """)).one()
            assert rls == (True, True)

        with runtime.begin() as connection:
            set_tenant_context(connection, clinic_a, user_a)
            session = {"clinic_id": clinic_a, "user_id": user_a}
            _require_activity_lead(connection, session, lead_a)
            with pytest.raises(HTTPException) as missing:
                _require_activity_lead(connection, session, lead_b)
            assert missing.value.status_code == 404
            # Deliberately omit clinic filtering to prove database RLS, not application SQL.
            assert connection.execute(text(
                "SELECT body FROM lead_activities"
            )).scalars().all() == ["Synthetic A note"]
            connection.execute(text("""
                INSERT INTO lead_activities
                    (clinic_id, lead_id, actor_user_id, kind, body, due_at)
                VALUES (:clinic_a, :lead_a, :user_a, 'follow_up', 'Synthetic callback',
                        '2026-10-02T09:00:00Z')
            """), values)
            for wrong_lead, wrong_author in ((lead_b, user_a), (lead_a, user_b)):
                with pytest.raises(IntegrityError), connection.begin_nested():
                    connection.execute(text("""
                        INSERT INTO lead_activities
                            (clinic_id, lead_id, actor_user_id, kind, body)
                        VALUES (:clinic_a, :lead_id, :author_id, 'note', 'Invalid link')
                    """), {**values, "lead_id": wrong_lead, "author_id": wrong_author})
            with pytest.raises(DBAPIError), connection.begin_nested():
                connection.execute(text("""
                    INSERT INTO lead_activities (clinic_id, lead_id, actor_user_id, kind, body)
                    VALUES (:clinic_b, :lead_b, :user_b, 'note', 'Cross-tenant write')
                """), values)
            for statement in (
                "UPDATE lead_activities SET body = 'Rewrite'",
                "DELETE FROM lead_activities",
            ):
                with pytest.raises(DBAPIError), connection.begin_nested():
                    connection.execute(text(statement))
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(text("""
                    INSERT INTO lead_activities (clinic_id, lead_id, actor_user_id, kind, body)
                    VALUES (:clinic_a, :lead_a, :user_a, 'follow_up', 'Missing due date')
                """), values)
            specialty_id = connection.execute(text(
                "SELECT id FROM specialties WHERE status = 'active' ORDER BY code LIMIT 1"
            )).scalar_one()
            scope_values = {**values, "specialty_id": specialty_id}
            connection.execute(text("""
                INSERT INTO clinic_specialties (clinic_id, specialty_id)
                VALUES (:clinic_a, :specialty_id)
            """), scope_values)
            connection.execute(text("""
                INSERT INTO user_specialty_scopes (clinic_id, user_id, specialty_id)
                VALUES (:clinic_a, :user_a, :specialty_id)
            """), scope_values)
            with pytest.raises(HTTPException) as wrong_specialty:
                _require_activity_lead(connection, session, lead_a)
            assert wrong_specialty.value.status_code == 404
            connection.execute(text("""
                UPDATE leads SET specialty_id = :specialty_id WHERE id = :lead_a
            """), scope_values)
            _require_activity_lead(connection, session, lead_a)
            branch_id = connection.execute(text("""
                INSERT INTO branches (clinic_id, code, name)
                VALUES (:clinic_a, 'ACTIVITY-TEST', 'Synthetic activity branch') RETURNING id
            """), values).scalar_one()
            connection.execute(text("""
                INSERT INTO user_branch_scopes (clinic_id, user_id, branch_id)
                VALUES (:clinic_a, :user_a, :branch_id)
            """), {**values, "branch_id": branch_id})
            # No linked appointment establishes a permitted branch for this lead.
            with pytest.raises(HTTPException) as wrong_branch:
                _require_activity_lead(connection, session, lead_a)
            assert wrong_branch.value.status_code == 404
    finally:
        with admin.begin() as connection:
            connection.execute(text(
                "DELETE FROM lead_activities WHERE clinic_id IN (:clinic_a, :clinic_b)"
            ), values)
            connection.execute(text(
                "DELETE FROM leads WHERE clinic_id IN (:clinic_a, :clinic_b)"
            ), values)
            connection.execute(text(
                "DELETE FROM users WHERE clinic_id IN (:clinic_a, :clinic_b)"
            ), values)
            connection.execute(text(
                "DELETE FROM branches WHERE clinic_id IN (:clinic_a, :clinic_b)"
            ), values)
            connection.execute(text(
                "DELETE FROM clinic_specialties WHERE clinic_id IN (:clinic_a, :clinic_b)"
            ), values)
            connection.execute(text(
                "DELETE FROM clinics WHERE id IN (:clinic_a, :clinic_b)"
            ), values)
        admin.dispose()
        runtime.dispose()
