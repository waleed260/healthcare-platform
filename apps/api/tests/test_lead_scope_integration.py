"""PostgreSQL evidence that specialty scope filters leads in list/detail and
blocks out-of-scope specialty assignment via PATCH. Skipped when integration
URLs are unset.
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.tenant import set_tenant_context
from app.modules.blueprint_core import routes
from app.modules.blueprint_core.schemas import LeadConvert, LeadUpdate


pytestmark = pytest.mark.integration


def _database_urls() -> tuple[str, str]:
    admin_url = os.getenv("TEST_ADMIN_DATABASE_URL")
    runtime_url = os.getenv("TEST_DATABASE_URL")
    if not admin_url or not runtime_url:
        pytest.skip("PostgreSQL integration URLs are not configured")
    return admin_url, runtime_url


def _request() -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())))


def test_specialty_scope_filters_list_and_blocks_out_of_scope_assignment(monkeypatch) -> None:
    admin_url, runtime_url = _database_urls()
    admin = create_engine(admin_url)
    runtime = create_engine(runtime_url, connect_args={"cursor_factory": psycopg.ClientCursor})
    runtime_session = sessionmaker(bind=runtime, autoflush=False, autocommit=False, expire_on_commit=False)

    clinic_id, user_id = uuid4(), uuid4()
    in_lead, out_lead, null_lead = uuid4(), uuid4(), uuid4()
    in_branch_lead, out_branch_lead = uuid4(), uuid4()

    def _fake_auth(db, *args, **kwargs):
        set_tenant_context(db, clinic_id, user_id)
        return {"clinic_id": clinic_id, "user_id": user_id}

    monkeypatch.setattr(routes, "_authorized", _fake_auth)
    monkeypatch.setattr(routes, "_write_authorized", _fake_auth)

    session = runtime_session()
    try:
        with admin.begin() as c:
            c.execute(text("INSERT INTO clinics (id, name, slug) VALUES (:id, 'Scope Clinic', :slug)"),
                      {"id": clinic_id, "slug": f"scope-{clinic_id}"})
            c.execute(text("INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash, status) VALUES (:id, :clinic_id, :email, 'Scoped User', 'unused', 'active')"),
                      {"id": user_id, "clinic_id": clinic_id, "email": f"scope-{user_id}@example.test"})
            in_spec = c.execute(text("SELECT id FROM specialties WHERE status = 'active' ORDER BY name LIMIT 1")).scalar_one()
            out_spec = c.execute(text("SELECT id FROM specialties WHERE status = 'active' AND id <> :a ORDER BY name LIMIT 1"), {"a": in_spec}).scalar_one()
            for sp in (in_spec, out_spec):
                c.execute(text("INSERT INTO clinic_specialties (clinic_id, specialty_id) VALUES (:c, :s)"),
                          {"c": clinic_id, "s": sp})
            c.execute(text("INSERT INTO user_specialty_scopes (clinic_id, user_id, specialty_id) VALUES (:c, :u, :s)"),
                      {"c": clinic_id, "u": user_id, "s": in_spec})
            c.execute(text("INSERT INTO leads (id, clinic_id, full_name, source, specialty_id) VALUES (:id, :c, 'In', 'call', :s)"),
                      {"id": in_lead, "c": clinic_id, "s": in_spec})
            c.execute(text("INSERT INTO leads (id, clinic_id, full_name, source, specialty_id) VALUES (:id, :c, 'Out', 'call', :s)"),
                      {"id": out_lead, "c": clinic_id, "s": out_spec})
            c.execute(text("INSERT INTO leads (id, clinic_id, full_name, source) VALUES (:id, :c, 'Null', 'call')"),
                      {"id": null_lead, "c": clinic_id})
            in_branch = c.execute(text("INSERT INTO branches (clinic_id, code, name) VALUES (:c, 'IN', 'In') RETURNING id"), {"c": clinic_id}).scalar_one()
            out_branch = c.execute(text("INSERT INTO branches (clinic_id, code, name) VALUES (:c, 'OUT', 'Out') RETURNING id"), {"c": clinic_id}).scalar_one()
            c.execute(text("INSERT INTO user_branch_scopes (clinic_id, user_id, branch_id) VALUES (:c, :u, :b)"),
                      {"c": clinic_id, "u": user_id, "b": in_branch})
            c.execute(text("INSERT INTO leads (id, clinic_id, full_name, source, specialty_id, branch_id) VALUES (:id, :c, 'InBranch', 'call', :s, :b)"),
                      {"id": in_branch_lead, "c": clinic_id, "s": in_spec, "b": in_branch})
            c.execute(text("INSERT INTO leads (id, clinic_id, full_name, source, specialty_id, branch_id) VALUES (:id, :c, 'OutBranch', 'call', :s, :b)"),
                      {"id": out_branch_lead, "c": clinic_id, "s": in_spec, "b": out_branch})

        listed = routes.lead_list(_request(), None, None, 50, session, "session")
        ids = {row["id"] for row in listed["data"]}
        assert in_branch_lead in ids  # specialty + branch both in scope
        assert in_lead not in ids  # branch-scoped user: NULL branch excluded
        assert out_lead not in ids  # specialty scope excludes
        assert null_lead not in ids  # NULL specialty excluded for scoped user
        assert out_branch_lead not in ids  # branch scope excludes

        with pytest.raises(HTTPException) as exc:
            routes.lead_detail(out_lead, _request(), session, "session")
        assert exc.value.status_code == 404
        with pytest.raises(HTTPException) as exc:
            routes.lead_detail(out_branch_lead, _request(), session, "session")
        assert exc.value.status_code == 404

        payload = LeadUpdate(expected_version=1, specialty_id=out_spec)
        with pytest.raises(HTTPException) as exc:
            routes.lead_update(in_branch_lead, payload, _request(), session, "session", "csrf")
        assert exc.value.status_code == 403
        payload = LeadUpdate(expected_version=1, branch_id=out_branch)
        with pytest.raises(HTTPException) as exc:
            routes.lead_update(in_branch_lead, payload, _request(), session, "session", "csrf")
        assert exc.value.status_code == 403

        # Lost leads cannot be converted (state-machine guard).
        routes.lead_update(in_branch_lead,
                           LeadUpdate(expected_version=1, status="lost", lost_reason="budget"),
                           _request(), session, "session", "csrf")
        with pytest.raises(HTTPException) as exc:
            routes.lead_convert(in_branch_lead, LeadConvert(), _request(), session, "session", "csrf")
        assert exc.value.status_code == 409
    finally:
        session.close()
        with admin.begin() as c:
            c.execute(text("DELETE FROM leads WHERE clinic_id = :c"), {"c": clinic_id})
            c.execute(text("DELETE FROM user_specialty_scopes WHERE clinic_id = :c"), {"c": clinic_id})
            c.execute(text("DELETE FROM user_branch_scopes WHERE clinic_id = :c"), {"c": clinic_id})
            c.execute(text("DELETE FROM branches WHERE clinic_id = :c"), {"c": clinic_id})
            c.execute(text("DELETE FROM clinic_specialties WHERE clinic_id = :c"), {"c": clinic_id})
            c.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
            c.execute(text("DELETE FROM clinics WHERE id = :c"), {"c": clinic_id})
