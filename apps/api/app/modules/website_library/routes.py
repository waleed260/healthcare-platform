from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, Request, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.audit.service import record_event
from app.modules.identity.routes import _error
from app.modules.website_library.schemas import ApplySiteTemplate, PageFromTemplate, ReusableCreate, ReusableInsert, ReusableUpdate, SectionReorder
from app.modules.website_library.templates import PAGE_BY_KEY, PAGE_TEMPLATES, SECTION_PRESETS, SITE_BY_KEY, SITE_TEMPLATES
from app.modules.websites.publishing import refresh_draft_snapshot
from app.modules.websites.routes import _authorized, _csrf
from app.modules.websites.sanitizer import sanitize_rich_text, validate_navigation_href
from app.modules.websites.schemas import SectionContent
from app.modules.websites.theme import normalize_brand

router = APIRouter(prefix="/api/v1/website-library", tags=["website-library"])


def _clean_content(content: dict) -> dict:
    cleaned = SectionContent.model_validate(content).model_dump()
    cleaned["body"] = sanitize_rich_text(cleaned["body"])
    cleaned["button_href"] = validate_navigation_href(cleaned.get("button_href"))
    return cleaned


def _write(request: Request, db: Session, session_token: str | None, csrf_token: str | None) -> dict:
    session = _authorized(db, session_token, "website.edit")
    _csrf(request, session, csrf_token)
    return session


def _insert_page(db: Session, clinic_id: UUID, website_id: UUID, page: dict, slug: str, title: str) -> UUID:
    row = db.execute(text("""
        INSERT INTO website_pages (clinic_id, website_id, slug, title, seo_title, seo_description)
        VALUES (:clinic_id, :website_id, :slug, :title, :seo_title, :seo_description) RETURNING id
    """), {"clinic_id": clinic_id, "website_id": website_id, "slug": slug, "title": title, "seo_title": page.get("seo_title"), "seo_description": page.get("seo_description")}).scalar_one()
    for position, section in enumerate(page["sections"]):
        db.execute(text("""
            INSERT INTO website_sections (clinic_id, page_id, section_type, layout_key, position, content)
            VALUES (:clinic_id, :page_id, :section_type, :layout_key, :position, CAST(:content AS jsonb))
        """), {"clinic_id": clinic_id, "page_id": row, "section_type": section["section_type"], "layout_key": section["layout_key"], "position": position, "content": json.dumps(_clean_content(section["content"]))})
    return row


@router.get("/templates")
def template_library(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "website.read")
    enabled = set(db.execute(text("""
        SELECT s.code FROM clinic_specialties cs JOIN specialties s ON s.id = cs.specialty_id
        WHERE cs.clinic_id = :clinic_id AND cs.status = 'active' AND cs.archived_at IS NULL
    """), {"clinic_id": session["clinic_id"]}).scalars().all())
    db.commit()
    sites = [{"key": t["key"], "name": t["name"], "specialty": t["specialty"], "description": t["description"], "template_key": t["template_key"], "page_count": len(t["pages"]), "locked": t["specialty"] != "general" and t["specialty"] not in enabled} for t in SITE_TEMPLATES]
    pages = [{"key": t["key"], "name": t["name"], "description": t["description"], "section_count": len(t["sections"])} for t in PAGE_TEMPLATES]
    return {"data": {"site_templates": sites, "page_templates": pages, "section_presets": SECTION_PRESETS}, "meta": {"request_id": request.state.request_id}}


@router.post("/websites/{website_id}/apply-site-template")
def apply_site_template(website_id: UUID, payload: ApplySiteTemplate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write(request, db, session_token, csrf_token)
    template = SITE_BY_KEY.get(payload.template_key)
    if template is None:
        raise _error("NOT_FOUND", "That website template does not exist.", status.HTTP_404_NOT_FOUND)
    clinic_id = session["clinic_id"]
    if template["specialty"] != "general":
        allowed = db.execute(text("""
            SELECT 1 FROM clinic_specialties cs JOIN specialties s ON s.id = cs.specialty_id
            WHERE cs.clinic_id = :clinic_id AND s.code = :code AND cs.status = 'active' AND cs.archived_at IS NULL
        """), {"clinic_id": clinic_id, "code": template["specialty"]}).scalar_one_or_none()
        if allowed is None:
            raise _error("SPECIALTY_LOCKED", "Enable this specialty before using its template.", status.HTTP_403_FORBIDDEN)
    website = db.execute(text("SELECT version, brand FROM websites WHERE clinic_id = :clinic_id AND id = :id AND archived_at IS NULL FOR UPDATE"), {"clinic_id": clinic_id, "id": website_id}).mappings().one_or_none()
    if website is None:
        raise _error("NOT_FOUND", "Website not found.", status.HTTP_404_NOT_FOUND)
    if website["version"] != payload.expected_version:
        raise _error("VERSION_CONFLICT", "The website changed before the template was applied.", status.HTTP_409_CONFLICT)
    if payload.apply_theme:
        brand = {**(website["brand"] or {}), **{key: template[key] for key in ("theme", "header", "footer")}}
        db.execute(text("UPDATE websites SET brand = CAST(:brand AS jsonb), template_key = :template_key WHERE clinic_id = :clinic_id AND id = :id"), {"brand": json.dumps(normalize_brand(brand)), "template_key": template["template_key"], "clinic_id": clinic_id, "id": website_id})
    existing = set(db.execute(text("SELECT slug FROM website_pages WHERE clinic_id = :clinic_id AND website_id = :id"), {"clinic_id": clinic_id, "id": website_id}).scalars().all())
    created = []
    for page in template["pages"]:
        if page["slug"] in existing:
            continue
        _insert_page(db, clinic_id, website_id, page, page["slug"], page["title"])
        created.append(page["slug"])
    record_event(db, clinic_id=clinic_id, actor_user_id=session["user_id"], action="website.template.apply", entity_type="website", entity_id=website_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"template": payload.template_key, "pages": created})
    refresh_draft_snapshot(db, clinic_id, website_id, session["user_id"])
    db.commit()
    return {"data": {"template_key": payload.template_key, "pages_created": created, "pages_kept": sorted(existing & {p["slug"] for p in template["pages"]})}, "meta": {"request_id": request.state.request_id}}


@router.post("/websites/{website_id}/pages-from-template", status_code=status.HTTP_201_CREATED)
def page_from_template(website_id: UUID, payload: PageFromTemplate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write(request, db, session_token, csrf_token)
    template = PAGE_BY_KEY.get(payload.template_key)
    if template is None:
        raise _error("NOT_FOUND", "That page template does not exist.", status.HTTP_404_NOT_FOUND)
    clinic_id = session["clinic_id"]
    if db.execute(text("SELECT 1 FROM websites WHERE clinic_id = :clinic_id AND id = :id AND archived_at IS NULL"), {"clinic_id": clinic_id, "id": website_id}).scalar_one_or_none() is None:
        raise _error("NOT_FOUND", "Website not found.", status.HTTP_404_NOT_FOUND)
    try:
        page_id = _insert_page(db, clinic_id, website_id, template, payload.slug, payload.title)
    except IntegrityError as exc:
        db.rollback()
        raise _error("DUPLICATE", "A page with this slug already exists for the website.", status.HTTP_409_CONFLICT) from exc
    record_event(db, clinic_id=clinic_id, actor_user_id=session["user_id"], action="website.page.from_template", entity_type="website_page", entity_id=page_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"template": payload.template_key})
    refresh_draft_snapshot(db, clinic_id, website_id, session["user_id"])
    db.commit()
    return {"data": {"id": page_id, "slug": payload.slug, "title": payload.title}, "meta": {"request_id": request.state.request_id}}


@router.get("/reusable-sections")
def reusable_list(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "website.read")
    rows = db.execute(text("""
        SELECT r.id, r.name, r.section_type, r.layout_key, r.content, r.version, r.updated_at,
               (SELECT COUNT(*) FROM website_sections s WHERE s.clinic_id = r.clinic_id AND s.reusable_section_id = r.id) AS synced_uses
        FROM reusable_sections r WHERE r.clinic_id = :clinic_id ORDER BY r.name LIMIT 200
    """), {"clinic_id": session["clinic_id"]}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.post("/reusable-sections", status_code=status.HTTP_201_CREATED)
def reusable_create(payload: ReusableCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write(request, db, session_token, csrf_token)
    try:
        row = db.execute(text("""
            INSERT INTO reusable_sections (clinic_id, name, section_type, layout_key, content, created_by)
            SELECT clinic_id, :name, section_type, layout_key, content, :user_id FROM website_sections WHERE clinic_id = :clinic_id AND id = :section_id
            RETURNING id, name, section_type, layout_key, content, version
        """), {"clinic_id": session["clinic_id"], "section_id": payload.source_section_id, "name": payload.name, "user_id": session["user_id"]}).mappings().one_or_none()
    except IntegrityError as exc:
        db.rollback()
        raise _error("DUPLICATE", "A reusable section with this name already exists.", status.HTTP_409_CONFLICT) from exc
    if row is None:
        raise _error("NOT_FOUND", "The source section was not found.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="website.reusable.create", entity_type="reusable_section", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.patch("/reusable-sections/{reusable_id}")
def reusable_update(reusable_id: UUID, payload: ReusableUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    """Editing a reusable section propagates to every synced instance's draft."""
    session = _write(request, db, session_token, csrf_token)
    if payload.name is None and payload.content is None:
        raise _error("INVALID_INPUT", "Provide a name or content to update.", status.HTTP_400_BAD_REQUEST)
    clinic_id = session["clinic_id"]
    content = _clean_content(payload.content.model_dump()) if payload.content is not None else None
    row = db.execute(text("""
        UPDATE reusable_sections SET name = COALESCE(:name, name), content = COALESCE(CAST(:content AS jsonb), content), version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND id = :id AND version = :expected_version
        RETURNING id, name, section_type, layout_key, content, version
    """), {"clinic_id": clinic_id, "id": reusable_id, "name": payload.name, "content": None if content is None else json.dumps(content), "expected_version": payload.expected_version}).mappings().one_or_none()
    if row is None:
        raise _error("VERSION_CONFLICT", "The reusable section changed or does not exist.", status.HTTP_409_CONFLICT)
    websites: list[UUID] = []
    if content is not None:
        websites = list(db.execute(text("""
            WITH updated AS (
                UPDATE website_sections SET content = CAST(:content AS jsonb), version = version + 1, updated_at = now()
                WHERE clinic_id = :clinic_id AND reusable_section_id = :id RETURNING page_id
            )
            SELECT DISTINCT p.website_id FROM updated u JOIN website_pages p ON p.clinic_id = :clinic_id AND p.id = u.page_id
        """), {"clinic_id": clinic_id, "id": reusable_id, "content": json.dumps(content)}).scalars().all())
        for website_id in websites:
            refresh_draft_snapshot(db, clinic_id, website_id, session["user_id"])
    record_event(db, clinic_id=clinic_id, actor_user_id=session["user_id"], action="website.reusable.update", entity_type="reusable_section", entity_id=reusable_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"websites_refreshed": len(websites)})
    db.commit()
    return {"data": {**dict(row), "websites_refreshed": len(websites)}, "meta": {"request_id": request.state.request_id}}


@router.delete("/reusable-sections/{reusable_id}")
def reusable_delete(reusable_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write(request, db, session_token, csrf_token)
    deleted = db.execute(text("DELETE FROM reusable_sections WHERE clinic_id = :clinic_id AND id = :id"), {"clinic_id": session["clinic_id"], "id": reusable_id}).rowcount
    if not deleted:
        raise _error("NOT_FOUND", "Reusable section not found.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="website.reusable.delete", entity_type="reusable_section", entity_id=reusable_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": {"deleted": True}, "meta": {"request_id": request.state.request_id}}


@router.post("/websites/{website_id}/pages/{page_id}/insert-reusable/{reusable_id}", status_code=status.HTTP_201_CREATED)
def reusable_insert(website_id: UUID, page_id: UUID, reusable_id: UUID, payload: ReusableInsert, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write(request, db, session_token, csrf_token)
    clinic_id = session["clinic_id"]
    row = db.execute(text("""
        INSERT INTO website_sections (clinic_id, page_id, section_type, layout_key, position, content, reusable_section_id)
        SELECT r.clinic_id, p.id, r.section_type, r.layout_key,
               COALESCE((SELECT MAX(position) + 1 FROM website_sections WHERE clinic_id = :clinic_id AND page_id = p.id), 0), r.content,
               CASE WHEN :mode = 'synced' THEN r.id ELSE NULL END
        FROM reusable_sections r, website_pages p
        WHERE r.clinic_id = :clinic_id AND r.id = :reusable_id AND p.clinic_id = :clinic_id AND p.id = :page_id AND p.website_id = :website_id
        RETURNING id, section_type, layout_key, position, content, is_visible, version, reusable_section_id
    """), {"clinic_id": clinic_id, "reusable_id": reusable_id, "page_id": page_id, "website_id": website_id, "mode": payload.mode}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "The page or reusable section was not found.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=clinic_id, actor_user_id=session["user_id"], action="website.reusable.insert", entity_type="website_section", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id), metadata={"mode": payload.mode})
    refresh_draft_snapshot(db, clinic_id, website_id, session["user_id"])
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.post("/websites/{website_id}/pages/{page_id}/reorder-sections")
def reorder_sections(website_id: UUID, page_id: UUID, payload: SectionReorder, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    """Atomically set the order of every section on a page (positions are unique per page)."""
    session = _write(request, db, session_token, csrf_token)
    clinic_id = session["clinic_id"]
    if len(set(payload.section_ids)) != len(payload.section_ids):
        raise _error("INVALID_INPUT", "Each section may appear only once.", status.HTTP_400_BAD_REQUEST)
    current = db.execute(text("""
        SELECT s.id FROM website_sections s JOIN website_pages p ON p.clinic_id = s.clinic_id AND p.id = s.page_id
        WHERE s.clinic_id = :clinic_id AND p.id = :page_id AND p.website_id = :website_id FOR UPDATE OF s
    """), {"clinic_id": clinic_id, "page_id": page_id, "website_id": website_id}).scalars().all()
    if set(current) != set(payload.section_ids):
        raise _error("VERSION_CONFLICT", "The page's sections changed. Reload and try again.", status.HTTP_409_CONFLICT)
    # Two phases so the (page, position) unique constraint is never violated mid-update.
    db.execute(text("UPDATE website_sections SET position = position + 1000 WHERE clinic_id = :clinic_id AND page_id = :page_id"), {"clinic_id": clinic_id, "page_id": page_id})
    for position, section_id in enumerate(payload.section_ids):
        db.execute(text("UPDATE website_sections SET position = :position, version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :id"), {"position": position, "clinic_id": clinic_id, "id": section_id})
    record_event(db, clinic_id=clinic_id, actor_user_id=session["user_id"], action="website.sections.reorder", entity_type="website_page", entity_id=page_id, outcome="success", request_id=UUID(request.state.request_id))
    refresh_draft_snapshot(db, clinic_id, website_id, session["user_id"])
    db.commit()
    return {"data": {"reordered": len(payload.section_ids)}, "meta": {"request_id": request.state.request_id}}
