"""PostgreSQL evidence that keyset pagination round-trips through a server-issued
cursor after the L2 change to explicit CAST(:param AS uuid/timestamptz) binding.

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

from app.db.tenant import set_tenant_context
from app.modules.blueprint_core import routes


pytestmark = pytest.mark.integration


def _database_urls() -> tuple[str, str]:
    admin_url = os.getenv("TEST_ADMIN_DATABASE_URL")
    runtime_url = os.getenv("TEST_DATABASE_URL")
    if not admin_url or not runtime_url:
        pytest.skip("PostgreSQL integration URLs are not configured")
    return admin_url, runtime_url


def _request() -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())))


def test_lead_list_cursor_round_trip_returns_next_page(monkeypatch) -> None:
    admin_url, runtime_url = _database_urls()
    admin = create_engine(admin_url)
    runtime = create_engine(runtime_url, connect_args={"cursor_factory": psycopg.ClientCursor})
    runtime_session = sessionmaker(bind=runtime, autoflush=False, autocommit=False, expire_on_commit=False)
    clinic_id, user_id = uuid4(), uuid4()
    lead_ids = [uuid4() for _ in range(3)]

    def _fake_auth(db, *args, **kwargs):
        set_tenant_context(db, clinic_id, user_id)
        return {"clinic_id": clinic_id, "user_id": user_id}

    monkeypatch.setattr(routes, "_authorized", _fake_auth)

    session = runtime_session()
    try:
        with admin.begin() as connection:
            connection.execute(text("INSERT INTO clinics (id, name, slug) VALUES (:id, 'Synthetic Paging', :slug)"), {"id": clinic_id, "slug": f"paging-{clinic_id}"})
            connection.execute(text("INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash, status) VALUES (:id, :clinic_id, :email, 'Synthetic Paging', 'unused', 'active')"), {"id": user_id, "clinic_id": clinic_id, "email": f"paging-{user_id}@example.test"})
            # Identical created_at across the three leads forces the (created_at, id)
            # composite tiebreaker — exactly what the CAST-bound keyset must handle.
            for index, lead_id in enumerate(lead_ids):
                connection.execute(text("INSERT INTO leads (id, clinic_id, full_name, source, created_at) VALUES (:id, :clinic_id, :name, 'call', now())"), {"id": lead_id, "clinic_id": clinic_id, "name": f"Synthetic Lead {index}"})

        first = routes.lead_list(_request(), None, None, 2, session, "session")
        assert len(first["data"]) == 2
        assert first["meta"]["next_cursor"] is not None

        second = routes.lead_list(_request(), None, first["meta"]["next_cursor"], 2, session, "session")
        assert len(second["data"]) == 1
        assert second["meta"]["next_cursor"] is None

        seen = [row["id"] for row in first["data"]] + [row["id"] for row in second["data"]]
        assert len(set(seen)) == 3  # no overlap, every lead returned exactly once
        assert set(seen) == set(lead_ids)
    finally:
        session.close()
        with admin.begin() as connection:
            connection.execute(text("DELETE FROM leads WHERE clinic_id = :clinic_id"), {"clinic_id": clinic_id})
            connection.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})
            connection.execute(text("DELETE FROM clinics WHERE id = :clinic_id"), {"clinic_id": clinic_id})
