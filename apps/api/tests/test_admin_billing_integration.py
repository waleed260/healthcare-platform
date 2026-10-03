"""PostgreSQL evidence that the platform-admin control room surfaces each
client's billing/subscription state (so unpaid clients can be found and have
their access turned off) and a billing breakdown in the metrics overview.

Runs in CI's PostgreSQL service; skipped when integration URLs are unset.
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.tenant import set_platform_context
from app.modules.governance import admin_routes

pytestmark = pytest.mark.integration


def _database_urls() -> tuple[str, str]:
    admin_url = os.getenv("TEST_ADMIN_DATABASE_URL")
    runtime_url = os.getenv("TEST_DATABASE_URL")
    if not admin_url or not runtime_url:
        pytest.skip("PostgreSQL integration URLs are not configured")
    return admin_url, runtime_url


def _request() -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())))


def test_admin_clinics_and_metrics_surface_billing_status(monkeypatch) -> None:
    admin_url, runtime_url = _database_urls()
    admin = create_engine(admin_url)
    runtime = create_engine(runtime_url, connect_args={"cursor_factory": psycopg.ClientCursor})
    runtime_session = sessionmaker(bind=runtime, autoflush=False, autocommit=False, expire_on_commit=False)
    clinic_id, admin_user_id, plan_id = uuid4(), uuid4(), uuid4()

    def _fake_platform(db, *args, **kwargs):
        set_platform_context(db, admin_user_id)
        return {"clinic_id": None, "user_id": admin_user_id}

    monkeypatch.setattr(admin_routes, "_platform", _fake_platform)

    session = runtime_session()
    try:
        with admin.begin() as connection:
            connection.execute(text("INSERT INTO clinics (id, name, slug, status) VALUES (:id, 'Synthetic Unpaid Client', :slug, 'active')"), {"id": clinic_id, "slug": f"unpaid-{clinic_id}"})
            connection.execute(text("INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash, status, is_platform_admin) VALUES (:id, NULL, :email, 'Synthetic Admin', 'unused', 'active', true)"), {"id": admin_user_id, "email": f"admin-{admin_user_id}@example.test"})
            connection.execute(text("INSERT INTO plans (id, code, name, active, monthly_price_minor, currency) VALUES (:id, :code, 'Synthetic Plan', true, 500000, 'PKR')"), {"id": plan_id, "code": f"syn-{uuid4().hex[:8]}"})
            # This client is past_due — they have not paid.
            connection.execute(text("INSERT INTO clinic_subscriptions (clinic_id, plan_id, status) VALUES (:clinic_id, :plan_id, 'past_due')"), {"clinic_id": clinic_id, "plan_id": plan_id})

        clinics = admin_routes.clinics_list(_request(), None, 100, session, "session")["data"]
        row = next((clinic for clinic in clinics if clinic["id"] == clinic_id), None)
        assert row is not None, "the new clinic must appear in the admin directory"
        assert row["subscription_status"] == "past_due"
        assert row["plan_name"] == "Synthetic Plan"

        metrics = admin_routes.metrics(_request(), session, "session")["data"]
        assert "billing" in metrics
        assert metrics["billing"]["past_due"] >= 1  # at least our unpaid client
    finally:
        session.close()
        with admin.begin() as connection:
            connection.execute(text("DELETE FROM clinic_subscriptions WHERE clinic_id = :clinic_id"), {"clinic_id": clinic_id})
            connection.execute(text("DELETE FROM users WHERE id = :id"), {"id": admin_user_id})
            connection.execute(text("DELETE FROM clinics WHERE id = :clinic_id"), {"clinic_id": clinic_id})
            connection.execute(text("DELETE FROM plans WHERE id = :id"), {"id": plan_id})
