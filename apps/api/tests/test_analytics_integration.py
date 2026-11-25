"""Integration tests for the operations analytics endpoints, against real PostgreSQL + RLS.

Previously skipped module-wide because the `client`/`auth_cookie` fixtures they were written
against were never implemented. Rewritten to the suite's direct-call integration style: a real
clinic/user plus a little domain data are seeded with the migrator role, the analytics route
functions run against a real runtime (RLS-enforced) session, and `_authorized` is stubbed to set
the real tenant context and return the seeded session (session-cookie auth itself is covered by
the identity tests). Auto-skips when the integration DB URLs are absent.
"""
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session as OrmSession

from app.db.tenant import set_tenant_context
from app.modules.operations import routes as operations_routes


pytestmark = pytest.mark.integration


def _request():
    return SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())))


@pytest.fixture
def analytics_env(monkeypatch):
    admin_url = os.getenv("TEST_ADMIN_DATABASE_URL")
    runtime_url = os.getenv("TEST_DATABASE_URL")
    if not admin_url or not runtime_url:
        pytest.skip("PostgreSQL integration URLs are not configured")
    admin = create_engine(admin_url)
    runtime = create_engine(runtime_url, connect_args={"cursor_factory": psycopg.ClientCursor})
    clinic_id, user_id = uuid4(), uuid4()
    branch_id, service_id, patient_id, appt_id = uuid4(), uuid4(), uuid4(), uuid4()
    now = datetime.now(timezone.utc)
    try:
        with admin.begin() as c:
            p = {"clinic": clinic_id, "user": user_id, "branch": branch_id, "service": service_id,
                 "patient": patient_id, "appt": appt_id, "t0": now, "t1": now + timedelta(minutes=30)}
            c.execute(text("INSERT INTO clinics (id, name, slug) VALUES (:clinic, 'Analytics Clinic', :slug)"), {**p, "slug": f"analytics-{clinic_id}"})
            c.execute(text("INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash) VALUES (:user, :clinic, :email, 'Analyst', 'unused')"), {**p, "email": f"analytics-{user_id}@example.test"})
            c.execute(text("INSERT INTO branches (id, clinic_id, code, name, status) VALUES (:branch, :clinic, 'ANB', 'Analytics Branch', 'active')"), p)
            c.execute(text("INSERT INTO services (id, clinic_id, name, duration_minutes) VALUES (:service, :clinic, 'Consultation', 30)"), p)
            c.execute(text("INSERT INTO patients (id, clinic_id, patient_number, full_name) VALUES (:patient, :clinic, 'P-ANALYTICS', 'Seed Patient')"), p)
            c.execute(text("""
                INSERT INTO appointments (id, clinic_id, branch_id, service_id, patient_id, status,
                    starts_at, ends_at, occupancy_start, occupancy_end, reference, idempotency_key, idempotency_body_hash)
                VALUES (:appt, :clinic, :branch, :service, :patient, 'confirmed', :t0, :t1, :t0, :t1, 'BK-AN', :key, 'h')
            """), {**p, "key": f"an-{appt_id}"})
            # Three leads across distinct sources/stages so the funnel and channel grouping are real.
            c.execute(text("INSERT INTO leads (clinic_id, full_name, source, status) VALUES (:clinic, 'New One', 'referral', 'new')"), p)
            c.execute(text("INSERT INTO leads (clinic_id, full_name, source, status) VALUES (:clinic, 'Qualified One', 'website', 'qualified')"), p)
            c.execute(text("INSERT INTO leads (clinic_id, full_name, source, status, converted_to_patient_id) VALUES (:clinic, 'Converted One', 'walk_in', 'converted', :patient)"), p)

        session = OrmSession(bind=runtime)
        monkeypatch.setattr(operations_routes, "_authorized", lambda db, token, permission, branch_id=None: (set_tenant_context(db, clinic_id, user_id), {"clinic_id": clinic_id, "user_id": user_id})[1])
        yield session
        session.close()
    finally:
        with admin.begin() as c:
            for table in ("appointments", "leads", "patients", "services", "branches", "users"):
                c.execute(text(f"DELETE FROM {table} WHERE clinic_id = :c"), {"c": clinic_id})
            c.execute(text("DELETE FROM clinics WHERE id = :c"), {"c": clinic_id})
        admin.dispose()
        runtime.dispose()


def test_daily_returns_complete_date_range(analytics_env):
    """GET /analytics/daily?range=7d returns exactly 8 rows (today + 7 prior days)."""
    data = operations_routes.analytics_daily(_request(), range="7d", db=analytics_env, session_token="x")["data"]
    assert len(data) == 8


def test_daily_zero_fills_missing_dates(analytics_env):
    """Days with no appointments still appear with zeroed (non-negative) counts."""
    data = operations_routes.analytics_daily(_request(), range="7d", db=analytics_env, session_token="x")["data"]
    for row in data:
        assert row["appointments"] >= 0
        assert row["no_shows"] >= 0
    # The seeded appointment lands on one day, proving the range is populated, not empty.
    assert sum(row["appointments"] for row in data) >= 1


def test_channels_groups_by_source(analytics_env):
    """GET /analytics/channels groups leads by source; channels are unique."""
    data = operations_routes.analytics_channels(_request(), range="30d", db=analytics_env, session_token="x")["data"]
    channels = [row["channel"] for row in data]
    assert len(channels) == len(set(channels))
    assert {"referral", "website", "walk_in"}.issubset(set(channels))


def test_funnel_stages_are_ordered(analytics_env):
    """GET /analytics/funnel returns the six pipeline stages in order."""
    data = operations_routes.analytics_funnel(_request(), range="30d", db=analytics_env, session_token="x")["data"]
    assert [step["stage"] for step in data] == ["new", "contacted", "qualified", "appointment_booked", "visited", "converted"]


def test_funnel_counts_decrease(analytics_env):
    """Each funnel stage count is <= the prior stage (cumulative fill over seeded leads)."""
    data = operations_routes.analytics_funnel(_request(), range="30d", db=analytics_env, session_token="x")["data"]
    for i in range(1, len(data)):
        assert data[i]["count"] <= data[i - 1]["count"]
    assert data[0]["count"] == 3   # all three non-lost seeded leads reach stage "new"
    assert data[-1]["count"] == 1  # one converted lead


def test_top_services_limited_to_10(analytics_env):
    """GET /analytics/top-services returns at most 10 services and includes the seeded one."""
    data = operations_routes.analytics_top_services(_request(), range="90d", db=analytics_env, session_token="x")["data"]
    assert len(data) <= 10
    assert any(row["name"] == "Consultation" for row in data)


def test_analytics_are_tenant_isolated(analytics_env):
    """A different clinic's tenant context sees none of this clinic's leads (RLS, not app SQL)."""
    foreign = uuid4()
    set_tenant_context(analytics_env, foreign, uuid4())
    leaked = analytics_env.execute(text("SELECT count(*) FROM leads")).scalar_one()
    analytics_env.rollback()
    assert leaked == 0
