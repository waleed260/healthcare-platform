"""PostgreSQL evidence that a section edit → publish actually propagates to the
public snapshot that the live site reads. Regression guard for the version-
conflict bug where refresh_draft_snapshot() bumped websites.version after every
section mutation, so a stale expected_version made publish silently 409 and
edits never reached the live_version.

Skipped when integration URLs are unset.
"""
from __future__ import annotations

import json
import os
from types import SimpleNamespace
from uuid import UUID, uuid4

import psycopg
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.tenant import set_tenant_context
from app.modules.websites import routes
from app.modules.websites.publishing import refresh_draft_snapshot
from app.modules.websites.schemas import (
    SectionContent,
    WebsitePublishRequest,
    WebsiteSectionEdit,
)


pytestmark = pytest.mark.integration


def _database_urls() -> tuple[str, str]:
    admin_url = os.getenv("TEST_ADMIN_DATABASE_URL")
    runtime_url = os.getenv("TEST_DATABASE_URL")
    if not admin_url or not runtime_url:
        pytest.skip("PostgreSQL integration URLs are not configured")
    return admin_url, runtime_url


def _request() -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())))


def test_section_edit_then_publish_reaches_public_snapshot(monkeypatch) -> None:
    admin_url, runtime_url = _database_urls()
    admin = create_engine(admin_url)
    runtime = create_engine(runtime_url, connect_args={"cursor_factory": psycopg.ClientCursor})
    runtime_session = sessionmaker(bind=runtime, autoflush=False, autocommit=False, expire_on_commit=False)

    clinic_id, user_id = uuid4(), uuid4()
    website_id, page_id, section_id = uuid4(), uuid4(), uuid4()
    slug = f"wp-{clinic_id.hex[:12]}"

    def _fake_auth(db, *args, **kwargs):
        set_tenant_context(db, clinic_id, user_id)
        return {"clinic_id": clinic_id, "user_id": user_id}

    monkeypatch.setattr(routes, "_authorized", _fake_auth)
    monkeypatch.setattr(routes, "_csrf", lambda *args, **kwargs: None)
    monkeypatch.setattr(routes, "_validate_origin", lambda *args, **kwargs: None)

    session = runtime_session()
    try:
        with admin.begin() as c:
            c.execute(text("INSERT INTO clinics (id, name, slug, status) VALUES (:id, 'Publish Clinic', :slug, 'active')"),
                      {"id": clinic_id, "slug": slug})
            c.execute(text("INSERT INTO users (id, clinic_id, normalized_email, display_name, password_hash, status) VALUES (:id, :clinic_id, :email, 'Publisher', 'unused', 'active')"),
                      {"id": user_id, "clinic_id": clinic_id, "email": f"publisher-{user_id}@example.test"})
            # Bypass website_create (which also writes theme_instances) and insert the
            # minimum rows this test needs. Starts at websites.version = 1.
            c.execute(text("INSERT INTO websites (id, clinic_id, name, template_key, brand) VALUES (:id, :c, 'Live Site', 'calm_clinic', CAST('{}' AS jsonb))"),
                      {"id": website_id, "c": clinic_id})
            c.execute(text("INSERT INTO website_pages (id, clinic_id, website_id, slug, title) VALUES (:id, :c, :w, 'home', 'Home')"),
                      {"id": page_id, "c": clinic_id, "w": website_id})
            for legal_slug, legal_title in (("privacy", "Privacy"), ("cancellation", "Cancellation"), ("medical-disclaimer", "Disclaimer")):
                c.execute(text("INSERT INTO website_pages (clinic_id, website_id, slug, title) VALUES (:c, :w, :slug, :title)"),
                          {"c": clinic_id, "w": website_id, "slug": legal_slug, "title": legal_title})
            c.execute(text("""
                INSERT INTO website_sections (id, clinic_id, page_id, section_type, layout_key, position, content, is_visible)
                VALUES (:id, :c, :p, 'hero', 'split', 0, CAST(:content AS jsonb), true)
            """), {"id": section_id, "c": clinic_id, "p": page_id,
                   "content": json.dumps({"heading": "Original heading", "body": "Original body."})})

        # Seed an initial draft version so publish has something to copy.
        set_tenant_context(session, clinic_id, user_id)
        refresh_draft_snapshot(session, clinic_id, website_id, user_id)
        session.commit()

        set_tenant_context(session, clinic_id, user_id)
        pre_version = session.execute(text("SELECT version FROM websites WHERE clinic_id = :c AND id = :w"), {"c": clinic_id, "w": website_id}).scalar_one()
        section_version = session.execute(text("SELECT version FROM website_sections WHERE clinic_id = :c AND id = :s"), {"c": clinic_id, "s": section_id}).scalar_one()

        edited_heading = f"Edited heading {uuid4().hex[:8]}"
        routes.section_update(
            website_id=website_id, page_id=page_id, section_id=section_id,
            payload=WebsiteSectionEdit(
                section_type="hero", layout_key="split", position=0,
                content=SectionContent(heading=edited_heading, body="Body after edit."),
                is_visible=True, expected_version=section_version,
            ),
            request=_request(), db=session, session_token="session", csrf_token="csrf",
        )
        set_tenant_context(session, clinic_id, user_id)
        post_edit_version = session.execute(text("SELECT version FROM websites WHERE clinic_id = :c AND id = :w"), {"c": clinic_id, "w": website_id}).scalar_one()
        assert post_edit_version > pre_version, "refresh_draft_snapshot must bump websites.version after an edit"

        # Publishing with the pre-edit version would 409; using the live version succeeds.
        published = routes.publish_website(
            website_id=website_id,
            payload=WebsitePublishRequest(expected_version=post_edit_version),
            request=_request(), db=session, session_token="session", csrf_token="csrf",
        )
        assert published["data"]["status"] == "published"
        assert published["data"]["live_version_id"] is not None

        # Public endpoint must return the edited heading in the live snapshot.
        public = routes.public_site_by_slug(clinic_slug=slug, request=_request(), db=session)
        snapshot_pages = public["data"]["snapshot"]["pages"]
        headings = [s["content"].get("heading") for p in snapshot_pages for s in p["sections"]]
        assert edited_heading in headings, f"edited heading missing from live snapshot: {headings}"
    finally:
        session.close()
        with admin.begin() as c:
            c.execute(text("DELETE FROM website_preview_tokens WHERE clinic_id = :c"), {"c": clinic_id})
            c.execute(text("DELETE FROM website_sections WHERE clinic_id = :c"), {"c": clinic_id})
            c.execute(text("DELETE FROM website_pages WHERE clinic_id = :c"), {"c": clinic_id})
            c.execute(text("DELETE FROM websites WHERE clinic_id = :c"), {"c": clinic_id})
            c.execute(text("DELETE FROM website_versions WHERE clinic_id = :c"), {"c": clinic_id})
            c.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
            c.execute(text("DELETE FROM clinics WHERE id = :c"), {"c": clinic_id})
