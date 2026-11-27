"""Inventory category CRUD against real PostgreSQL + RLS.

Regression for the Inventory Categories repair: a valid category is created and listed, a
duplicate slug is rejected, categories are tenant-isolated (one clinic never sees another's), and
the slug-uniqueness is per clinic (two clinics may reuse the same slug). Auth is stubbed the way
the suite stubs direct route calls; the tenant filter + RLS run for real. Auto-skips without URLs.
"""
import os
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session as OrmSession

from app.db.tenant import set_tenant_context
from app.modules.inventory import routes as inv_routes
from app.modules.inventory.schemas import InventoryCategoryCreate


pytestmark = pytest.mark.integration


def _req():
    return SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())))


@pytest.fixture
def inv_env(monkeypatch):
    admin_url, runtime_url = os.getenv("TEST_ADMIN_DATABASE_URL"), os.getenv("TEST_DATABASE_URL")
    if not admin_url or not runtime_url:
        pytest.skip("PostgreSQL integration URLs are not configured")
    admin = create_engine(admin_url)
    runtime = create_engine(runtime_url, connect_args={"cursor_factory": psycopg.ClientCursor})
    a_clinic, a_user, b_clinic, b_user = uuid4(), uuid4(), uuid4(), uuid4()
    ctx = {"clinic": a_clinic, "user": a_user}
    try:
        with admin.begin() as c:
            for cl, us, tag in ((a_clinic, a_user, "a"), (b_clinic, b_user, "b")):
                c.execute(text("INSERT INTO clinics (id, name, slug) VALUES (:c, 'Inv', :s)"), {"c": cl, "s": f"inv-{tag}-{cl}"})
                c.execute(text("INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash) VALUES (:u, :c, :e, 'S', 'x')"), {"u": us, "c": cl, "e": f"inv-{us}@x.test"})

        def _auth(db, token, permission, branch_id=None):
            set_tenant_context(db, ctx["clinic"], ctx["user"]); return {"clinic_id": ctx["clinic"], "user_id": ctx["user"]}
        monkeypatch.setattr(inv_routes, "_authorized", _auth)
        monkeypatch.setattr(inv_routes, "_write_authorized", lambda db, request, token, permission, csrf, branch_id=None: _auth(db, token, permission))
        session = OrmSession(bind=runtime)
        yield session, ctx, {"a_clinic": a_clinic, "a_user": a_user, "b_clinic": b_clinic, "b_user": b_user}
        session.close()
    finally:
        with admin.begin() as c:
            for cl in (a_clinic, b_clinic):
                c.execute(text("DELETE FROM inventory_categories WHERE clinic_id = :c"), {"c": cl})
                c.execute(text("DELETE FROM users WHERE clinic_id = :c"), {"c": cl})
                c.execute(text("DELETE FROM clinics WHERE id = :c"), {"c": cl})
        admin.dispose(); runtime.dispose()


def test_category_create_list_duplicate_and_tenant_isolation(inv_env):
    session, ctx, ids = inv_env

    created = inv_routes.category_create(InventoryCategoryCreate(name="Surgical Tools", slug="surgical-tools"), _req(), db=session, session_token="x", csrf_token="x")["data"]
    assert created["name"] == "Surgical Tools" and created["slug"] == "surgical-tools"

    # It is listed back for clinic A.
    names_a = [r["slug"] for r in inv_routes.category_list(_req(), db=session, session_token="x")["data"]]
    assert "surgical-tools" in names_a

    # Duplicate slug within the same clinic is rejected.
    with pytest.raises(HTTPException) as dup:
        inv_routes.category_create(InventoryCategoryCreate(name="Again", slug="surgical-tools"), _req(), db=session, session_token="x", csrf_token="x")
    assert dup.value.detail["error"]["code"] == "DUPLICATE"

    # Switch to clinic B: it sees none of clinic A's categories (RLS), and may reuse the same slug.
    ctx["clinic"], ctx["user"] = ids["b_clinic"], ids["b_user"]
    names_b = [r["slug"] for r in inv_routes.category_list(_req(), db=session, session_token="x")["data"]]
    assert "surgical-tools" not in names_b
    reused = inv_routes.category_create(InventoryCategoryCreate(name="Surgical Tools", slug="surgical-tools"), _req(), db=session, session_token="x", csrf_token="x")["data"]
    assert reused["slug"] == "surgical-tools"  # per-clinic slug uniqueness, not global
