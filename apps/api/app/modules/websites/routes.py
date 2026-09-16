import json
import hashlib
import re
import secrets
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, Request, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.tenant import set_tenant_context
from app.core.security import hash_token
from app.modules.authorization.service import ForbiddenError, require_permission
from app.modules.identity.routes import _error, _session_or_401, _validate_origin
from app.modules.identity.service import SessionError, verify_csrf
from app.modules.websites.sanitizer import sanitize_rich_text, validate_navigation_href
from app.modules.websites.dns import DnsLookupUnavailable, lookup_txt_proofs, verification_record_name
from app.modules.audit.service import record_event
from app.modules.websites.publishing import refresh_draft_snapshot, snapshot_checksum, validate_publish_snapshot
from app.modules.websites.scanner import MAX_WEBSITE_IMAGE_BYTES, validate_image_magic
from app.modules.files.storage import delete_private_object, put_private_object, put_public_object, read_private_object, read_public_object
from app.modules.websites.schemas import DomainCreate, DomainVerify, WebsiteArchiveRequest, WebsiteCreate, WebsiteMediaCreate, WebsiteMediaUpdate, WebsitePageCreate, WebsitePageUpdate, WebsitePublishRequest, WebsiteRollbackRequest, WebsiteSectionEdit, WebsiteSectionUpdate, WebsiteUpdate, WebsiteVersionCommand

router = APIRouter(prefix="/api/v1/websites", tags=["websites"])
public_router = APIRouter(prefix="/api/v1/public/sites", tags=["public-websites"])


def _authorized(db: Session, session_token: str | None, permission: str) -> dict:
    session = _session_or_401(db, session_token)
    if session["clinic_id"] is None:
        raise _error("FORBIDDEN", "A clinic context is required.", status.HTTP_403_FORBIDDEN)
    set_tenant_context(db, session["clinic_id"], session["user_id"])
    try:
        require_permission(db, session["user_id"], session["clinic_id"], permission)
    except ForbiddenError as exc:
        raise _error("FORBIDDEN", "You do not have permission for this website.", status.HTTP_403_FORBIDDEN) from exc
    return session


@router.get("")
def website_list(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "website.read")
    rows = db.execute(text("SELECT id, name, template_key, status, draft_version_id, live_version_id, version, created_at, updated_at FROM websites WHERE clinic_id = :clinic_id AND archived_at IS NULL ORDER BY created_at DESC, id"), {"clinic_id": session["clinic_id"]}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.post("", status_code=status.HTTP_201_CREATED)
def website_create(payload: WebsiteCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _authorized(db, session_token, "website.edit")
    _csrf(request, session, csrf_token)
    row = db.execute(text("INSERT INTO websites (clinic_id, name, template_key, brand) VALUES (:clinic_id, :name, :template_key, CAST(:brand AS jsonb)) RETURNING id, name, template_key, brand, status, version, created_at"), {"clinic_id": session["clinic_id"], "name": payload.name.strip(), "template_key": payload.template_key, "brand": json.dumps(payload.brand)}).mappings().one()
    draft = refresh_draft_snapshot(db, session["clinic_id"], row["id"], session["user_id"])
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="website.create", entity_type="website", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": {**dict(row), "draft_version_id": draft["id"]}, "meta": {"request_id": request.state.request_id}}


@router.patch("/{website_id}")
def website_update(website_id: UUID, payload: WebsiteUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _authorized(db, session_token, "website.edit")
    _csrf(request, session, csrf_token)
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    if not values:
        raise _error("INVALID_INPUT", "At least one website field is required.", status.HTTP_400_BAD_REQUEST)
    params = {"clinic_id": session["clinic_id"], "website_id": website_id, "expected_version": payload.expected_version}
    assignments = []
    for field, value in values.items():
        assignments.append(f"{field} = CAST(:{field} AS jsonb)" if field == "brand" else f"{field} = :{field}")
        params[field] = json.dumps(value) if field == "brand" else value
    row = db.execute(text(f"""
        UPDATE websites SET {', '.join(assignments)}, version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND id = :website_id AND archived_at IS NULL AND version = :expected_version
        RETURNING id, name, template_key, brand, status, version, updated_at
    """), params).mappings().one_or_none()
    if row is None:
        raise _error("VERSION_CONFLICT", "The website changed before update.", status.HTTP_409_CONFLICT)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="website.update", entity_type="website", entity_id=website_id, outcome="success", request_id=UUID(request.state.request_id))
    refresh_draft_snapshot(db, session["clinic_id"], website_id, session["user_id"])
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.post("/{website_id}/archive")
def website_archive(website_id: UUID, payload: WebsiteArchiveRequest, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _authorized(db, session_token, "website.edit")
    _csrf(request, session, csrf_token)
    row = db.execute(text("""
        UPDATE websites SET archived_at = now(), status = 'archived', version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND id = :website_id AND archived_at IS NULL AND version = :expected_version
        RETURNING id, status, archived_at, version
    """), {"clinic_id": session["clinic_id"], "website_id": website_id, "expected_version": payload.expected_version}).mappings().one_or_none()
    if row is None:
        raise _error("VERSION_CONFLICT", "The website changed before archiving.", status.HTTP_409_CONFLICT)
    db.execute(text("UPDATE website_preview_tokens SET revoked_at = now() WHERE clinic_id = :clinic_id AND website_id = :website_id AND revoked_at IS NULL"), {"clinic_id": session["clinic_id"], "website_id": website_id})
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="website.archive", entity_type="website", entity_id=website_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.get("/{website_id}/versions")
def version_list(website_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "website.read")
    rows = db.execute(text("""
        SELECT id, version_number, schema_version, checksum, created_by, published_at, created_at
        FROM website_versions
        WHERE clinic_id = :clinic_id AND website_id = :website_id
        ORDER BY version_number DESC, id DESC
    """), {"clinic_id": session["clinic_id"], "website_id": website_id}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.get("/{website_id}/pages")
def page_list(website_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "website.read")
    rows = db.execute(text("SELECT id, slug, title, seo_title, seo_description, version, created_at, updated_at FROM website_pages WHERE clinic_id = :clinic_id AND website_id = :website_id ORDER BY slug, id"), {"clinic_id": session["clinic_id"], "website_id": website_id}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.post("/{website_id}/pages", status_code=status.HTTP_201_CREATED)
def page_create(website_id: UUID, payload: WebsitePageCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _authorized(db, session_token, "website.edit")
    _csrf(request, session, csrf_token)
    try:
        row = db.execute(text("INSERT INTO website_pages (clinic_id, website_id, slug, title, seo_title, seo_description) SELECT :clinic_id, id, :slug, :title, :seo_title, :seo_description FROM websites WHERE clinic_id = :clinic_id AND id = :website_id AND archived_at IS NULL RETURNING id, slug, title, seo_title, seo_description, version, created_at"), {"clinic_id": session["clinic_id"], "website_id": website_id, **payload.model_dump()}).mappings().one_or_none()
    except Exception as exc:
        db.rollback()
        raise _error("DUPLICATE", "A page with this slug already exists for the website.", status.HTTP_409_CONFLICT) from exc
    if row is None:
        raise _error("NOT_FOUND", "Website not found.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="website.page.create", entity_type="website_page", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id))
    refresh_draft_snapshot(db, session["clinic_id"], website_id, session["user_id"])
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.patch("/{website_id}/pages/{page_id}")
def page_update(website_id: UUID, page_id: UUID, payload: WebsitePageUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _authorized(db, session_token, "website.edit")
    _csrf(request, session, csrf_token)
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    if not values:
        raise _error("INVALID_INPUT", "At least one page field is required.", status.HTTP_400_BAD_REQUEST)
    assignments = [f"{field} = :{field}" for field in values]
    row = db.execute(text(f"""
        UPDATE website_pages
        SET {', '.join(assignments)}, version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND website_id = :website_id AND id = :page_id
          AND version = :expected_version
        RETURNING id, slug, title, seo_title, seo_description, version, updated_at
    """), {"clinic_id": session["clinic_id"], "website_id": website_id, "page_id": page_id, "expected_version": payload.expected_version, **values}).mappings().one_or_none()
    if row is None:
        exists = db.execute(text("SELECT version FROM website_pages WHERE clinic_id = :clinic_id AND website_id = :website_id AND id = :page_id"), {"clinic_id": session["clinic_id"], "website_id": website_id, "page_id": page_id}).scalar_one_or_none()
        raise _error("VERSION_CONFLICT" if exists is not None else "NOT_FOUND", "The page changed before update." if exists is not None else "Website page not found.", status.HTTP_409_CONFLICT if exists is not None else status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="website.page.update", entity_type="website_page", entity_id=page_id, outcome="success", request_id=UUID(request.state.request_id))
    refresh_draft_snapshot(db, session["clinic_id"], website_id, session["user_id"])
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.delete("/{website_id}/pages/{page_id}")
def page_delete(website_id: UUID, page_id: UUID, payload: WebsiteVersionCommand, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _authorized(db, session_token, "website.edit")
    _csrf(request, session, csrf_token)
    deleted = db.execute(text("""
        DELETE FROM website_pages
        WHERE clinic_id = :clinic_id AND website_id = :website_id AND id = :page_id AND version = :expected_version
        RETURNING id
    """), {"clinic_id": session["clinic_id"], "website_id": website_id, "page_id": page_id, "expected_version": payload.expected_version}).scalar_one_or_none()
    if deleted is None:
        exists = db.execute(text("SELECT version FROM website_pages WHERE clinic_id = :clinic_id AND website_id = :website_id AND id = :page_id"), {"clinic_id": session["clinic_id"], "website_id": website_id, "page_id": page_id}).scalar_one_or_none()
        raise _error("VERSION_CONFLICT" if exists is not None else "NOT_FOUND", "The page changed before deletion." if exists is not None else "Website page not found.", status.HTTP_409_CONFLICT if exists is not None else status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="website.page.delete", entity_type="website_page", entity_id=page_id, outcome="success", request_id=UUID(request.state.request_id))
    refresh_draft_snapshot(db, session["clinic_id"], website_id, session["user_id"])
    db.commit()
    return {"data": {"id": deleted, "deleted": True}, "meta": {"request_id": request.state.request_id}}


@router.get("/{website_id}/pages/{page_id}/sections")
def section_list(website_id: UUID, page_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "website.read")
    rows = db.execute(text("""
        SELECT s.id, s.section_type, s.layout_key, s.position, s.content, s.is_visible, s.version, s.created_at, s.updated_at
        FROM website_sections s
        JOIN website_pages p ON p.clinic_id = s.clinic_id AND p.id = s.page_id
        WHERE s.clinic_id = :clinic_id AND p.website_id = :website_id AND p.id = :page_id
        ORDER BY s.position, s.id
    """), {"clinic_id": session["clinic_id"], "website_id": website_id, "page_id": page_id}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.patch("/{website_id}/pages/{page_id}/sections/{section_id}")
def section_update(website_id: UUID, page_id: UUID, section_id: UUID, payload: WebsiteSectionEdit, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _authorized(db, session_token, "website.edit")
    _csrf(request, session, csrf_token)
    content = payload.content.model_dump()
    content["body"] = sanitize_rich_text(content["body"])
    try:
        content["button_href"] = validate_navigation_href(content.get("button_href"))
    except ValueError as exc:
        raise _error("INVALID_INPUT", str(exc), status.HTTP_400_BAD_REQUEST) from exc
    row = db.execute(text("""
        UPDATE website_sections s
        SET section_type = :section_type, layout_key = :layout_key, position = :position,
            content = CAST(:content AS jsonb), is_visible = :is_visible,
            version = version + 1, updated_at = now()
        FROM website_pages p
        WHERE s.clinic_id = :clinic_id AND s.id = :section_id AND s.page_id = p.id
          AND p.clinic_id = :clinic_id AND p.id = :page_id AND p.website_id = :website_id
          AND s.version = :expected_version
        RETURNING s.id, s.section_type, s.layout_key, s.position, s.content, s.is_visible, s.version, s.updated_at
    """), {"clinic_id": session["clinic_id"], "website_id": website_id, "page_id": page_id, "section_id": section_id, "expected_version": payload.expected_version, "section_type": payload.section_type, "layout_key": payload.layout_key, "position": payload.position, "content": json.dumps(content), "is_visible": payload.is_visible}).mappings().one_or_none()
    if row is None:
        exists = db.execute(text("""
            SELECT s.version FROM website_sections s JOIN website_pages p ON p.clinic_id = s.clinic_id AND p.id = s.page_id
            WHERE s.clinic_id = :clinic_id AND s.id = :section_id AND p.id = :page_id AND p.website_id = :website_id
        """), {"clinic_id": session["clinic_id"], "website_id": website_id, "page_id": page_id, "section_id": section_id}).scalar_one_or_none()
        raise _error("VERSION_CONFLICT" if exists is not None else "NOT_FOUND", "The section changed before update." if exists is not None else "Website section not found.", status.HTTP_409_CONFLICT if exists is not None else status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="website.section.update", entity_type="website_section", entity_id=section_id, outcome="success", request_id=UUID(request.state.request_id))
    refresh_draft_snapshot(db, session["clinic_id"], website_id, session["user_id"])
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.delete("/{website_id}/pages/{page_id}/sections/{section_id}")
def section_delete(website_id: UUID, page_id: UUID, section_id: UUID, payload: WebsiteVersionCommand, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _authorized(db, session_token, "website.edit")
    _csrf(request, session, csrf_token)
    deleted = db.execute(text("""
        DELETE FROM website_sections s
        USING website_pages p
        WHERE s.clinic_id = :clinic_id AND s.id = :section_id AND s.page_id = p.id
          AND p.clinic_id = :clinic_id AND p.id = :page_id AND p.website_id = :website_id
          AND s.version = :expected_version
        RETURNING s.id
    """), {"clinic_id": session["clinic_id"], "website_id": website_id, "page_id": page_id, "section_id": section_id, "expected_version": payload.expected_version}).scalar_one_or_none()
    if deleted is None:
        exists = db.execute(text("SELECT s.version FROM website_sections s JOIN website_pages p ON p.clinic_id = s.clinic_id AND p.id = s.page_id WHERE s.clinic_id = :clinic_id AND s.id = :section_id AND p.id = :page_id AND p.website_id = :website_id"), {"clinic_id": session["clinic_id"], "website_id": website_id, "page_id": page_id, "section_id": section_id}).scalar_one_or_none()
        raise _error("VERSION_CONFLICT" if exists is not None else "NOT_FOUND", "The section changed before deletion." if exists is not None else "Website section not found.", status.HTTP_409_CONFLICT if exists is not None else status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="website.section.delete", entity_type="website_section", entity_id=section_id, outcome="success", request_id=UUID(request.state.request_id))
    refresh_draft_snapshot(db, session["clinic_id"], website_id, session["user_id"])
    db.commit()
    return {"data": {"id": deleted, "deleted": True}, "meta": {"request_id": request.state.request_id}}


@router.post("/{website_id}/pages/{page_id}/sections", status_code=status.HTTP_201_CREATED)
def add_section(website_id: UUID, page_id: UUID, payload: WebsiteSectionUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    _validate_origin(request)
    session = _authorized(db, session_token, "website.edit")
    if not csrf_token:
        raise _error("CSRF_REQUIRED", "A CSRF token is required.", status.HTTP_403_FORBIDDEN)
    try:
        verify_csrf(session, csrf_token)
    except SessionError as exc:
        raise _error("CSRF_INVALID", "The CSRF token is invalid.", status.HTTP_403_FORBIDDEN) from exc
    content = payload.content.model_dump()
    content["body"] = sanitize_rich_text(content["body"])
    try:
        content["button_href"] = validate_navigation_href(content.get("button_href"))
    except ValueError as exc:
        db.rollback()
        raise _error("INVALID_INPUT", str(exc), status.HTTP_400_BAD_REQUEST) from exc
    row = db.execute(text("""
        INSERT INTO website_sections (clinic_id, page_id, section_type, layout_key, position, content, is_visible)
        SELECT :clinic_id, page.id, :section_type, :layout_key, :position, CAST(:content AS jsonb), :is_visible
        FROM website_pages page
        WHERE page.id = :page_id AND page.website_id = :website_id AND page.clinic_id = :clinic_id
        RETURNING id, section_type, layout_key, position, content, is_visible, version
    """), {"clinic_id": session["clinic_id"], "page_id": page_id, "website_id": website_id, "section_type": payload.section_type, "layout_key": payload.layout_key, "position": payload.position, "content": __import__("json").dumps(content), "is_visible": payload.is_visible}).mappings().one_or_none()
    if row is None:
        db.rollback()
        raise _error("NOT_FOUND", "The website page was not found.", status.HTTP_404_NOT_FOUND)
    refresh_draft_snapshot(db, session["clinic_id"], website_id, session["user_id"])
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


def _csrf(request: Request, session: dict, csrf_token: str | None) -> None:
    _validate_origin(request)
    if not csrf_token:
        raise _error("CSRF_REQUIRED", "A CSRF token is required.", status.HTTP_403_FORBIDDEN)
    try:
        verify_csrf(session, csrf_token)
    except SessionError as exc:
        raise _error("CSRF_INVALID", "The CSRF token is invalid.", status.HTTP_403_FORBIDDEN) from exc


def _hostname(value: str) -> str:
    normalized = value.strip().rstrip(".").casefold()
    if len(normalized) > 253 or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", normalized) or ".." in normalized or "." not in normalized:
        raise _error("INVALID_INPUT", "A valid fully-qualified hostname is required.", status.HTTP_400_BAD_REQUEST)
    return normalized


def _public_clinic_id(db: Session, hostname: str) -> UUID | None:
    """Resolve a verified hostname, then validate its clinic inside RLS."""
    clinic_id = db.execute(
        text("SELECT clinic_id FROM domain_verifications WHERE hostname = :hostname AND observed_status = 'verified'"),
        {"hostname": hostname},
    ).scalar_one_or_none()
    if clinic_id is None:
        return None
    set_tenant_context(db, clinic_id)
    active = db.execute(
        text("SELECT id FROM clinics WHERE id = :clinic_id AND status = 'active' AND archived_at IS NULL"),
        {"clinic_id": clinic_id},
    ).scalar_one_or_none()
    return active


def _media_extension(mime_type: str) -> str:
    return {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(mime_type, ".bin")


@router.get("/media")
def media_list(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "website.read")
    rows = db.execute(text("SELECT id, alt_text, mime_type, scan_status, is_public, version, created_at FROM website_media WHERE clinic_id = :clinic_id ORDER BY created_at DESC, id"), {"clinic_id": session["clinic_id"]}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.post("/media", status_code=status.HTTP_201_CREATED)
def media_create(payload: WebsiteMediaCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _authorized(db, session_token, "website.edit")
    _csrf(request, session, csrf_token)
    extension = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[payload.mime_type]
    storage_key = f"website-drafts/{session['clinic_id']}/{secrets.token_urlsafe(24)}{extension}"
    row = db.execute(text("INSERT INTO website_media (clinic_id, storage_key, alt_text, mime_type) VALUES (:clinic_id, :storage_key, :alt_text, :mime_type) RETURNING id, alt_text, mime_type, scan_status, is_public, version, created_at"), {"clinic_id": session["clinic_id"], "storage_key": storage_key, "alt_text": payload.alt_text.strip(), "mime_type": payload.mime_type}).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="website.media_create", entity_type="website_media", entity_id=row["id"], outcome="pending_scan", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id, "upload_status": "pending_scan"}}


@router.post("/media/upload", status_code=status.HTTP_201_CREATED)
async def media_upload(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"), original_filename: str | None = Header(default=None, alias="X-Original-Filename"), alt_text: str | None = Header(default=None, alias="X-Alt-Text"), content_type: str | None = Header(default=None, alias="Content-Type")) -> dict:
    session = _authorized(db, session_token, "website.edit")
    _csrf(request, session, csrf_token)
    filename = (original_filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    mime_type = (content_type or "").split(";", 1)[0].strip().casefold()
    allowed = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    if not filename or "\x00" in filename or mime_type not in allowed or not (alt_text or "").strip():
        raise _error("INVALID_INPUT", "A filename, alt text, and supported image MIME type are required.", status.HTTP_400_BAD_REQUEST)
    content = await request.body()
    if not content or len(content) > MAX_WEBSITE_IMAGE_BYTES:
        raise _error("FILE_TOO_LARGE", "Website images must be no larger than 8 MiB.", status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    if not filename.casefold().endswith(allowed[mime_type]):
        raise _error("INVALID_INPUT", "The filename extension does not match the MIME type.", status.HTTP_400_BAD_REQUEST)
    try:
        validate_image_magic(mime_type, content[:16])
    except ValueError as exc:
        raise _error("INVALID_INPUT", str(exc), status.HTTP_400_BAD_REQUEST) from exc
    media_id = UUID(secrets.token_hex(16))
    storage_key = f"website-drafts/{session['clinic_id']}/{media_id}{allowed[mime_type]}"
    digest = hashlib.sha256(content).hexdigest()
    try:
        put_private_object(storage_key, content)
        row = db.execute(text("""
            INSERT INTO website_media (id, clinic_id, storage_key, original_filename, alt_text, mime_type, size_bytes, content_sha256)
            VALUES (:id, :clinic_id, :storage_key, :filename, :alt_text, :mime_type, :size_bytes, :digest)
            RETURNING id, original_filename, alt_text, mime_type, size_bytes, scan_status, is_public, version, created_at
        """), {"id": media_id, "clinic_id": session["clinic_id"], "storage_key": storage_key, "filename": filename, "alt_text": alt_text.strip(), "mime_type": mime_type, "size_bytes": len(content), "digest": digest}).mappings().one()
        db.execute(text("INSERT INTO background_jobs (clinic_id, job_key, job_type) VALUES (:clinic_id, :job_key, 'website_media_scan') ON CONFLICT (clinic_id, job_key) DO NOTHING"), {"clinic_id": session["clinic_id"], "job_key": f"website-media-scan:{media_id}"})
    except Exception:
        db.rollback()
        raise
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="website.media_upload", entity_type="website_media", entity_id=media_id, outcome="pending_scan", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id, "upload_status": "pending_scan"}}


@router.patch("/media/{media_id}")
def media_update(media_id: UUID, payload: WebsiteMediaUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _authorized(db, session_token, "website.edit")
    _csrf(request, session, csrf_token)
    row = db.execute(text("""
        UPDATE website_media
        SET alt_text = :alt_text, version = version + 1
        WHERE clinic_id = :clinic_id AND id = :id AND is_public = false AND version = :expected_version
        RETURNING id, alt_text, mime_type, scan_status, is_public, version
    """), {"clinic_id": session["clinic_id"], "id": media_id, "alt_text": payload.alt_text.strip(), "expected_version": payload.expected_version}).mappings().one_or_none()
    if row is None:
        exists = db.execute(text("SELECT version, is_public FROM website_media WHERE clinic_id = :clinic_id AND id = :id"), {"clinic_id": session["clinic_id"], "id": media_id}).mappings().one_or_none()
        if exists is None:
            raise _error("NOT_FOUND", "Website media not found.", status.HTTP_404_NOT_FOUND)
        raise _error("VERSION_CONFLICT" if not exists["is_public"] else "INVALID_STATE", "The media changed before update." if not exists["is_public"] else "Published media cannot be edited.", status.HTTP_409_CONFLICT if not exists["is_public"] else status.HTTP_400_BAD_REQUEST)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="website.media_update", entity_type="website_media", entity_id=media_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.delete("/media/{media_id}")
def media_delete(media_id: UUID, payload: WebsiteVersionCommand, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _authorized(db, session_token, "website.edit")
    _csrf(request, session, csrf_token)
    deleted = db.execute(text("DELETE FROM website_media WHERE clinic_id = :clinic_id AND id = :id AND is_public = false AND version = :expected_version RETURNING id, storage_key"), {"clinic_id": session["clinic_id"], "id": media_id, "expected_version": payload.expected_version}).mappings().one_or_none()
    if deleted is None:
        exists = db.execute(text("SELECT version, is_public FROM website_media WHERE clinic_id = :clinic_id AND id = :id"), {"clinic_id": session["clinic_id"], "id": media_id}).mappings().one_or_none()
        if exists is None:
            raise _error("NOT_FOUND", "Draft media not found or already public.", status.HTTP_404_NOT_FOUND)
        raise _error("VERSION_CONFLICT" if not exists["is_public"] else "INVALID_STATE", "The media changed before deletion." if not exists["is_public"] else "Published media cannot be deleted.", status.HTTP_409_CONFLICT if not exists["is_public"] else status.HTTP_400_BAD_REQUEST)
    try:
        delete_private_object(deleted["storage_key"])
    except (FileNotFoundError, ValueError):
        pass
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="website.media_delete", entity_type="website_media", entity_id=media_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": {"id": deleted["id"], "deleted": True}, "meta": {"request_id": request.state.request_id}}


@router.get("/domains")
def domain_list(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "website.read")
    rows = db.execute(text("SELECT id, hostname, observed_status, certificate_status, checked_at, failure_reason, created_at FROM domain_verifications WHERE clinic_id = :clinic_id ORDER BY hostname"), {"clinic_id": session["clinic_id"]}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.post("/{website_id}/preview-token")
def preview_token_create(website_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _authorized(db, session_token, "website.read")
    _csrf(request, session, csrf_token)
    website = db.execute(text("SELECT id FROM websites WHERE clinic_id = :clinic_id AND id = :id AND archived_at IS NULL"), {"clinic_id": session["clinic_id"], "id": website_id}).scalar_one_or_none()
    if website is None:
        raise _error("NOT_FOUND", "Website not found.", status.HTTP_404_NOT_FOUND)
    token = secrets.token_urlsafe(32)
    row = db.execute(text("INSERT INTO website_preview_tokens (clinic_id, website_id, token_hash, expires_at, created_by) VALUES (:clinic_id, :website_id, :token_hash, now() + interval '15 minutes', :user_id) RETURNING id, expires_at"), {"clinic_id": session["clinic_id"], "website_id": website_id, "token_hash": hash_token(token), "user_id": session["user_id"]}).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="website.preview_token_create", entity_type="website", entity_id=website_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": {"preview_token": token, "expires_at": row["expires_at"]}, "meta": {"request_id": request.state.request_id, "token_returned_once": True}}


@router.post("/domains", status_code=status.HTTP_201_CREATED)
def domain_create(payload: DomainCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _authorized(db, session_token, "website.edit")
    _csrf(request, session, csrf_token)
    hostname = _hostname(payload.hostname)
    proof = secrets.token_urlsafe(32)
    try:
        row = db.execute(text("INSERT INTO domain_verifications (clinic_id, hostname, expected_dns_proof) VALUES (:clinic_id, :hostname, :proof) RETURNING id, hostname, observed_status, certificate_status, created_at"), {"clinic_id": session["clinic_id"], "hostname": hostname, "proof": hash_token(proof)}).mappings().one()
    except Exception as exc:
        db.rollback()
        raise _error("DUPLICATE", "That hostname is already registered.", status.HTTP_409_CONFLICT) from exc
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="website.domain_create", entity_type="domain_verification", entity_id=row["id"], outcome="pending", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": {**dict(row), "dns_proof": proof, "dns_record_name": verification_record_name(hostname)}, "meta": {"request_id": request.state.request_id, "proof_returned_once": True}}


@router.post("/domains/{domain_id}/verify")
def domain_verify(domain_id: UUID, payload: DomainVerify, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _authorized(db, session_token, "website.edit")
    _csrf(request, session, csrf_token)
    domain = db.execute(text("SELECT id, hostname, expected_dns_proof FROM domain_verifications WHERE clinic_id = :clinic_id AND id = :id"), {"clinic_id": session["clinic_id"], "id": domain_id}).mappings().one_or_none()
    if domain is None:
        raise _error("NOT_FOUND", "Domain verification not found.", status.HTTP_404_NOT_FOUND)
    try:
        proofs = lookup_txt_proofs(domain["hostname"])
    except DnsLookupUnavailable as exc:
        raise _error("DNS_CHECK_UNAVAILABLE", "DNS verification is temporarily unavailable.", status.HTTP_503_SERVICE_UNAVAILABLE) from exc
    if hash_token(payload.observed_proof) != domain["expected_dns_proof"] or payload.observed_proof not in proofs:
        raise _error("INVALID_PROOF", "The DNS proof did not match the registered hostname.", status.HTTP_400_BAD_REQUEST)
    row = db.execute(text("UPDATE domain_verifications SET observed_status = 'verified', certificate_status = 'pending', checked_at = now(), failure_reason = NULL WHERE clinic_id = :clinic_id AND id = :id RETURNING id, hostname, observed_status, certificate_status, checked_at"), {"clinic_id": session["clinic_id"], "id": domain_id}).mappings().one()
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="website.domain_verify", entity_type="domain_verification", entity_id=domain_id, outcome="verified", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.post("/{website_id}/publish")
def publish_website(website_id: UUID, payload: WebsitePublishRequest, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _authorized(db, session_token, "website.publish")
    _csrf(request, session, csrf_token)
    website = db.execute(text("SELECT id, draft_version_id, version FROM websites WHERE clinic_id = :clinic_id AND id = :id AND archived_at IS NULL FOR UPDATE"), {"clinic_id": session["clinic_id"], "id": website_id}).mappings().one_or_none()
    if website is None:
        raise _error("NOT_FOUND", "Website not found.", status.HTTP_404_NOT_FOUND)
    if website["version"] != payload.expected_version:
        raise _error("VERSION_CONFLICT", "The website changed before publishing.", status.HTTP_409_CONFLICT)
    if website["draft_version_id"] is None:
        raise _error("INVALID_STATE", "The website has no draft version.", status.HTTP_400_BAD_REQUEST)
    draft = db.execute(text("SELECT id, snapshot FROM website_versions WHERE clinic_id = :clinic_id AND id = :id AND website_id = :website_id"), {"clinic_id": session["clinic_id"], "id": website["draft_version_id"], "website_id": website_id}).mappings().one_or_none()
    if draft is None:
        raise _error("NOT_FOUND", "Draft version not found.", status.HTTP_404_NOT_FOUND)
    media_rows = db.execute(text("SELECT id, storage_key, mime_type FROM website_media WHERE clinic_id = :clinic_id AND is_public = false AND scan_status = 'clean' FOR UPDATE"), {"clinic_id": session["clinic_id"]}).mappings().all()
    pending_media = db.execute(text("SELECT COUNT(*) FROM website_media WHERE clinic_id = :clinic_id AND is_public = false AND scan_status <> 'clean'"), {"clinic_id": session["clinic_id"]}).scalar_one()
    if pending_media:
        raise _error("PUBLISH_VALIDATION_FAILED", "All website media must pass scanning before publishing.", status.HTTP_400_BAD_REQUEST)
    try:
        validate_publish_snapshot(draft["snapshot"])
    except ValueError as exc:
        raise _error("PUBLISH_VALIDATION_FAILED", str(exc), status.HTTP_400_BAD_REQUEST) from exc
    for media in media_rows:
        public_key = f"website-public/{session['clinic_id']}/{draft['id']}/{media['id']}{_media_extension(media['mime_type'])}"
        try:
            put_public_object(public_key, read_private_object(media["storage_key"]))
        except (FileNotFoundError, ValueError) as exc:
            raise _error("PUBLISH_VALIDATION_FAILED", "A website asset is unavailable for publishing.", status.HTTP_400_BAD_REQUEST) from exc
        db.execute(text("UPDATE website_media SET is_public = true, public_storage_key = :public_key WHERE clinic_id = :clinic_id AND id = :id"), {"public_key": public_key, "clinic_id": session["clinic_id"], "id": media["id"]})
    updated = db.execute(text("UPDATE websites SET live_version_id = :version_id, status = 'published', version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :id RETURNING id, live_version_id, status, version, updated_at"), {"clinic_id": session["clinic_id"], "id": website_id, "version_id": draft["id"]}).mappings().one()
    db.execute(text("UPDATE website_preview_tokens SET revoked_at = now() WHERE clinic_id = :clinic_id AND website_id = :website_id AND revoked_at IS NULL"), {"clinic_id": session["clinic_id"], "website_id": website_id})
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="website.publish", entity_type="website", entity_id=website_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(updated), "meta": {"request_id": request.state.request_id}}


@router.post("/{website_id}/rollback", status_code=status.HTTP_201_CREATED)
def rollback_website(website_id: UUID, payload: WebsiteRollbackRequest, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _authorized(db, session_token, "website.publish")
    _csrf(request, session, csrf_token)
    website = db.execute(text("SELECT id, version FROM websites WHERE clinic_id = :clinic_id AND id = :id AND archived_at IS NULL FOR UPDATE"), {"clinic_id": session["clinic_id"], "id": website_id}).mappings().one_or_none()
    if website is None:
        raise _error("NOT_FOUND", "Website not found.", status.HTTP_404_NOT_FOUND)
    if website["version"] != payload.expected_version:
        raise _error("VERSION_CONFLICT", "The website changed before rollback.", status.HTTP_409_CONFLICT)
    source = db.execute(text("SELECT snapshot, schema_version FROM website_versions WHERE clinic_id = :clinic_id AND id = :source AND website_id = :website_id"), {"clinic_id": session["clinic_id"], "source": payload.source_version_id, "website_id": website_id}).mappings().one_or_none()
    if source is None:
        raise _error("NOT_FOUND", "Source version not found.", status.HTTP_404_NOT_FOUND)
    try:
        validate_publish_snapshot(source["snapshot"])
    except ValueError as exc:
        raise _error("PUBLISH_VALIDATION_FAILED", str(exc), status.HTTP_400_BAD_REQUEST) from exc
    next_number = db.execute(text("SELECT COALESCE(MAX(version_number), 0) + 1 FROM website_versions WHERE clinic_id = :clinic_id AND website_id = :website_id"), {"clinic_id": session["clinic_id"], "website_id": website_id}).scalar_one()
    replacement = db.execute(text("INSERT INTO website_versions (clinic_id, website_id, version_number, schema_version, snapshot, checksum, created_by, published_at) VALUES (:clinic_id, :website_id, :version_number, :schema_version, CAST(:snapshot AS jsonb), :checksum, :created_by, now()) RETURNING id, version_number, checksum"), {"clinic_id": session["clinic_id"], "website_id": website_id, "version_number": next_number, "schema_version": source["schema_version"], "snapshot": json.dumps(source["snapshot"]), "checksum": snapshot_checksum(source["snapshot"]), "created_by": session["user_id"]}).mappings().one()
    updated = db.execute(text("UPDATE websites SET live_version_id = :version_id, draft_version_id = :version_id, status = 'published', version = version + 1, updated_at = now() WHERE clinic_id = :clinic_id AND id = :id RETURNING id, live_version_id, version"), {"clinic_id": session["clinic_id"], "id": website_id, "version_id": replacement["id"]}).mappings().one()
    db.execute(text("UPDATE website_preview_tokens SET revoked_at = now() WHERE clinic_id = :clinic_id AND website_id = :website_id AND revoked_at IS NULL"), {"clinic_id": session["clinic_id"], "website_id": website_id})
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="website.rollback", entity_type="website", entity_id=website_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": {"website": dict(updated), "replacement_version": dict(replacement)}, "meta": {"request_id": request.state.request_id}}


@public_router.get("/{hostname}/preview")
def public_site_preview(hostname: str, response: Response, request: Request, preview_token: str = Header(min_length=20, max_length=200, alias="X-Preview-Token"), db: Session = Depends(get_db)) -> dict:
    normalized = _hostname(hostname)
    clinic_id = _public_clinic_id(db, normalized)
    if clinic_id is None:
        raise _error("NOT_FOUND", "Website not found.", status.HTTP_404_NOT_FOUND)
    row = db.execute(text("""
        SELECT w.id, v.id AS version_id, v.snapshot
        FROM website_preview_tokens p
        JOIN websites w ON w.clinic_id = p.clinic_id AND w.id = p.website_id
        JOIN website_versions v ON v.clinic_id = w.clinic_id AND v.id = w.draft_version_id
        WHERE p.clinic_id = :clinic_id AND p.token_hash = :token_hash
          AND p.revoked_at IS NULL AND p.expires_at > now() AND w.archived_at IS NULL
    """), {"clinic_id": clinic_id, "token_hash": hash_token(preview_token)}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Website preview not found.", status.HTTP_404_NOT_FOUND)
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    db.commit()
    return {"data": {"website_id": row["id"], "version_id": row["version_id"], "snapshot": row["snapshot"]}, "meta": {"request_id": request.state.request_id, "preview": True}}


@public_router.get("/{hostname}/media/{media_id}")
def public_media(hostname: str, media_id: UUID, request: Request, db: Session = Depends(get_db)) -> Response:
    normalized = _hostname(hostname)
    clinic_id = _public_clinic_id(db, normalized)
    if clinic_id is None:
        raise _error("NOT_FOUND", "Website asset not found.", status.HTTP_404_NOT_FOUND)
    row = db.execute(text("SELECT public_storage_key, mime_type FROM website_media WHERE clinic_id = :clinic_id AND id = :id AND is_public = true"), {"clinic_id": clinic_id, "id": media_id}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Website asset not found.", status.HTTP_404_NOT_FOUND)
    try:
        content = read_public_object(row["public_storage_key"])
    except (FileNotFoundError, ValueError) as exc:
        raise _error("NOT_FOUND", "Website asset not found.", status.HTTP_404_NOT_FOUND) from exc
    db.commit()
    return Response(content=content, media_type=row["mime_type"], headers={"Cache-Control": "public, max-age=31536000, immutable"})


@public_router.get("/{hostname}")
def public_site(hostname: str, request: Request, db: Session = Depends(get_db)) -> dict:
    normalized = _hostname(hostname)
    clinic_id = _public_clinic_id(db, normalized)
    row = db.execute(text("""
        SELECT w.id, w.live_version_id, v.snapshot
        FROM websites w JOIN website_versions v ON v.clinic_id = w.clinic_id AND v.id = w.live_version_id
        WHERE w.clinic_id = :clinic_id AND w.status = 'published' AND w.archived_at IS NULL
    """), {"clinic_id": clinic_id}).mappings().one_or_none() if clinic_id is not None else None
    if row is None:
        raise _error("NOT_FOUND", "Website not found.", status.HTTP_404_NOT_FOUND)
    return {"data": {"website_id": row["id"], "snapshot": row["snapshot"]}, "meta": {"request_id": request.state.request_id, "cache_control": "public, max-age=60"}}
