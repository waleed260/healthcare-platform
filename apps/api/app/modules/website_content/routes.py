from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, Query, Request, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.tenant import set_tenant_context
from app.modules.appointments.rate_limit import consume_public_management_limit
from app.modules.audit.service import record_event
from app.modules.identity.routes import _error
from app.modules.website_content.schemas import FormCreate, FormUpdate, PostCreate, PostStatus, PostUpdate, TestimonialCreate, TestimonialModerate, validate_answers, FormSubmission
from app.modules.websites.routes import _authorized, _csrf, _public_slug_clinic_id
from app.modules.websites.sanitizer import sanitize_rich_text

router = APIRouter(prefix="/api/v1/website-content", tags=["website-content"])
public_router = APIRouter(prefix="/api/v1/public/sites/slug/{clinic_slug}", tags=["public-website-content"])


def _write(request: Request, db: Session, session_token: str | None, csrf_token: str | None, permission: str = "website.edit") -> dict:
    session = _authorized(db, session_token, permission)
    _csrf(request, session, csrf_token)
    return session


def _audit(db: Session, session: dict, request: Request, action: str, entity: str, entity_id: UUID, **metadata: object) -> None:
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action=action, entity_type=entity, entity_id=entity_id, outcome="success", request_id=UUID(request.state.request_id), metadata=metadata or None)


# ---------------------------------------------------------------- forms
_FORM_COLUMNS = "id, name, fields, action, specialty_id, branch_id, notify_user_ids, success_message, status, version, updated_at"


def _check_form_refs(db: Session, clinic_id: UUID, specialty_id: UUID | None, branch_id: UUID | None, notify: list[UUID]) -> None:
    if specialty_id is not None and db.execute(text("SELECT 1 FROM clinic_specialties WHERE clinic_id = :c AND specialty_id = :s AND status = 'active' AND archived_at IS NULL"), {"c": clinic_id, "s": specialty_id}).scalar_one_or_none() is None:
        raise _error("INVALID_INPUT", "That specialty is not enabled for this clinic.", status.HTTP_400_BAD_REQUEST)
    if branch_id is not None and db.execute(text("SELECT 1 FROM branches WHERE clinic_id = :c AND id = :b AND archived_at IS NULL"), {"c": clinic_id, "b": branch_id}).scalar_one_or_none() is None:
        raise _error("INVALID_INPUT", "That branch does not exist.", status.HTTP_400_BAD_REQUEST)
    if notify:
        found = db.execute(text("SELECT COUNT(*) FROM users WHERE clinic_id = :c AND id = ANY(:ids) AND status = 'active'"), {"c": clinic_id, "ids": notify}).scalar_one()
        if found != len(set(notify)):
            raise _error("INVALID_INPUT", "Every notified staff member must be an active user of this clinic.", status.HTTP_400_BAD_REQUEST)


@router.get("/forms")
def form_list(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "website.read")
    rows = db.execute(text(f"SELECT {_FORM_COLUMNS} FROM website_forms WHERE clinic_id = :c ORDER BY name LIMIT 100"), {"c": session["clinic_id"]}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.post("/forms", status_code=status.HTTP_201_CREATED)
def form_create(payload: FormCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write(request, db, session_token, csrf_token)
    _check_form_refs(db, session["clinic_id"], payload.specialty_id, payload.branch_id, payload.notify_user_ids)
    try:
        row = db.execute(text(f"""
            INSERT INTO website_forms (clinic_id, name, fields, action, specialty_id, branch_id, notify_user_ids, success_message)
            VALUES (:c, :name, CAST(:fields AS jsonb), :action, :specialty_id, :branch_id, :notify, :success)
            RETURNING {_FORM_COLUMNS}
        """), {"c": session["clinic_id"], "name": payload.name, "fields": json.dumps([f.model_dump() for f in payload.fields]), "action": payload.action, "specialty_id": payload.specialty_id, "branch_id": payload.branch_id, "notify": payload.notify_user_ids, "success": payload.success_message}).mappings().one()
    except IntegrityError as exc:
        db.rollback()
        raise _error("DUPLICATE", "A form with this name already exists.", status.HTTP_409_CONFLICT) from exc
    _audit(db, session, request, "website.form.create", "website_form", row["id"])
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.patch("/forms/{form_id}")
def form_update(form_id: UUID, payload: FormUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write(request, db, session_token, csrf_token)
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    if not values:
        raise _error("INVALID_INPUT", "Provide at least one field to update.", status.HTTP_400_BAD_REQUEST)
    _check_form_refs(db, session["clinic_id"], values.get("specialty_id"), values.get("branch_id"), values.get("notify_user_ids") or [])
    columns = {"name": "name", "fields": "fields", "action": "action", "specialty_id": "specialty_id", "branch_id": "branch_id", "notify_user_ids": "notify_user_ids", "success_message": "success_message", "status": "status"}
    assignments, params = [], {"c": session["clinic_id"], "id": form_id, "v": payload.expected_version}
    for key, value in values.items():
        assignments.append(f"{columns[key]} = CAST(:{key} AS jsonb)" if key == "fields" else f"{columns[key]} = :{key}")
        params[key] = json.dumps([f if isinstance(f, dict) else f for f in value]) if key == "fields" else value
    try:
        row = db.execute(text(f"UPDATE website_forms SET {', '.join(assignments)}, version = version + 1, updated_at = now() WHERE clinic_id = :c AND id = :id AND version = :v RETURNING {_FORM_COLUMNS}"), params).mappings().one_or_none()
    except IntegrityError as exc:
        db.rollback()
        raise _error("DUPLICATE", "A form with this name already exists.", status.HTTP_409_CONFLICT) from exc
    if row is None:
        raise _error("VERSION_CONFLICT", "The form changed or does not exist.", status.HTTP_409_CONFLICT)
    _audit(db, session, request, "website.form.update", "website_form", form_id)
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@public_router.get("/forms/{form_id}")
def public_form(clinic_slug: str, form_id: UUID, request: Request, db: Session = Depends(get_db)) -> dict:
    clinic_id = _public_slug_clinic_id(db, clinic_slug)
    row = db.execute(text("SELECT id, name, fields, success_message FROM website_forms WHERE clinic_id = :c AND id = :id AND status = 'active'"), {"c": clinic_id, "id": form_id}).mappings().one_or_none() if clinic_id else None
    if row is None:
        raise _error("NOT_FOUND", "Form not found.", status.HTTP_404_NOT_FOUND)
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id, "cache_control": "public, max-age=60"}}


@public_router.post("/forms/{form_id}/submit", status_code=status.HTTP_201_CREATED)
def public_form_submit(clinic_slug: str, form_id: UUID, payload: FormSubmission, request: Request, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), db: Session = Depends(get_db)) -> dict:
    clinic_id = _public_slug_clinic_id(db, clinic_slug)
    if clinic_id is None:
        raise _error("NOT_FOUND", "Form not found.", status.HTTP_404_NOT_FOUND)
    if not idempotency_key or not idempotency_key.strip() or len(idempotency_key.strip()) > 128:
        raise _error("INVALID_INPUT", "An Idempotency-Key header is required.", status.HTTP_400_BAD_REQUEST)
    form = db.execute(text("SELECT id, name, fields, action, specialty_id, branch_id, notify_user_ids, success_message FROM website_forms WHERE clinic_id = :c AND id = :id AND status = 'active'"), {"c": clinic_id, "id": form_id}).mappings().one_or_none()
    if form is None:
        raise _error("NOT_FOUND", "Form not found.", status.HTTP_404_NOT_FOUND)
    if not consume_public_management_limit(db, clinic_id=clinic_id, reference="website-form", ip_address=request.client.host if request.client else "unknown", maximum=10):
        db.rollback()
        raise _error("RATE_LIMITED", "Too many form submissions. Try again shortly.", status.HTTP_429_TOO_MANY_REQUESTS)
    try:
        cleaned = validate_answers(form["fields"], payload.answers)
    except ValueError as exc:
        db.rollback()
        raise _error("INVALID_INPUT", str(exc), status.HTTP_400_BAD_REQUEST) from exc
    mapped = {field["maps_to"]: cleaned.get(field["key"]) for field in form["fields"] if field.get("maps_to")}
    notes = [f"Form: {form['name']}"] + [f"{field['label']}: {cleaned[field['key']]}" for field in form["fields"] if field["key"] in cleaned and not field.get("maps_to") and field["type"] != "consent"]
    if mapped.get("notes"):
        notes.append(mapped["notes"])
    if form["branch_id"]:
        branch = db.execute(text("SELECT name FROM branches WHERE clinic_id = :c AND id = :b"), {"c": clinic_id, "b": form["branch_id"]}).scalar_one_or_none()
        if branch:
            notes.append(f"Branch: {branch}")
    campaign = "appointment-request" if form["action"] == "appointment_request" else f"form:{form['name']}"[:160]
    phone = "".join(ch for ch in (mapped.get("phone") or "") if ch.isdigit() or ch == "+") or None
    email = (mapped.get("email") or "").casefold() or None
    key = f"form:{form_id}:{idempotency_key.strip()}"[:200]
    lead = db.execute(text("""
        INSERT INTO leads (clinic_id, full_name, normalized_email, normalized_phone, source, campaign, specialty_id, notes, intake_key)
        VALUES (:c, :name, :email, :phone, 'website', :campaign, :specialty_id, :notes, :key)
        ON CONFLICT (clinic_id, intake_key) DO NOTHING RETURNING id
    """), {"c": clinic_id, "name": (mapped.get("full_name") or "").strip()[:160], "email": email, "phone": phone, "campaign": campaign, "specialty_id": form["specialty_id"], "notes": "\n".join(notes)[:5000], "key": key}).scalar_one_or_none()
    duplicate = lead is None
    if lead is not None:
        for user_id in form["notify_user_ids"]:
            db.execute(text("INSERT INTO notifications (clinic_id, user_id, kind, title, body) VALUES (:c, :u, 'lead.new', :title, :body) ON CONFLICT DO NOTHING"), {"c": clinic_id, "u": user_id, "title": f"New {'appointment request' if form['action'] == 'appointment_request' else 'enquiry'}: {mapped.get('full_name', '')[:80]}", "body": f"Submitted via “{form['name']}”."})
    db.commit()
    return {"data": {"duplicate": duplicate, "message": form["success_message"]}, "meta": {"request_id": request.state.request_id}}


# ---------------------------------------------------------------- blog
_POST_COLUMNS = "id, slug, title, excerpt, body, status, published_at, seo_title, seo_description, version, created_at, updated_at"


@router.get("/posts")
def post_list(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "website.read")
    rows = db.execute(text(f"SELECT {_POST_COLUMNS} FROM website_posts WHERE clinic_id = :c AND status <> 'archived' ORDER BY updated_at DESC LIMIT 100"), {"c": session["clinic_id"]}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.post("/posts", status_code=status.HTTP_201_CREATED)
def post_create(payload: PostCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write(request, db, session_token, csrf_token)
    try:
        row = db.execute(text(f"""
            INSERT INTO website_posts (clinic_id, slug, title, excerpt, body, seo_title, seo_description, author_user_id)
            VALUES (:c, :slug, :title, :excerpt, :body, :seo_title, :seo_description, :user) RETURNING {_POST_COLUMNS}
        """), {"c": session["clinic_id"], "user": session["user_id"], **payload.model_dump() | {"body": sanitize_rich_text(payload.body)}}).mappings().one()
    except IntegrityError as exc:
        db.rollback()
        raise _error("DUPLICATE", "A post with this slug already exists.", status.HTTP_409_CONFLICT) from exc
    _audit(db, session, request, "website.post.create", "website_post", row["id"])
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.patch("/posts/{post_id}")
def post_update(post_id: UUID, payload: PostUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write(request, db, session_token, csrf_token)
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    if not values:
        raise _error("INVALID_INPUT", "Provide at least one field to update.", status.HTTP_400_BAD_REQUEST)
    if "body" in values and values["body"] is not None:
        values["body"] = sanitize_rich_text(values["body"])
    assignments = ", ".join(f"{key} = :{key}" for key in values)
    try:
        row = db.execute(text(f"UPDATE website_posts SET {assignments}, version = version + 1, updated_at = now() WHERE clinic_id = :c AND id = :id AND version = :v RETURNING {_POST_COLUMNS}"), {"c": session["clinic_id"], "id": post_id, "v": payload.expected_version, **values}).mappings().one_or_none()
    except IntegrityError as exc:
        db.rollback()
        raise _error("DUPLICATE", "A post with this slug already exists.", status.HTTP_409_CONFLICT) from exc
    if row is None:
        raise _error("VERSION_CONFLICT", "The post changed or does not exist.", status.HTTP_409_CONFLICT)
    _audit(db, session, request, "website.post.update", "website_post", post_id)
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.post("/posts/{post_id}/status")
def post_status(post_id: UUID, payload: PostStatus, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write(request, db, session_token, csrf_token, "website.publish")
    row = db.execute(text(f"""
        UPDATE website_posts SET status = :status, published_at = CASE WHEN :status = 'published' THEN COALESCE(published_at, now()) ELSE published_at END, version = version + 1, updated_at = now()
        WHERE clinic_id = :c AND id = :id AND version = :v RETURNING {_POST_COLUMNS}
    """), {"c": session["clinic_id"], "id": post_id, "v": payload.expected_version, "status": payload.status}).mappings().one_or_none()
    if row is None:
        raise _error("VERSION_CONFLICT", "The post changed or does not exist.", status.HTTP_409_CONFLICT)
    _audit(db, session, request, f"website.post.{payload.status}", "website_post", post_id)
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@public_router.get("/posts")
def public_posts(clinic_slug: str, request: Request, limit: int = Query(default=20, ge=1, le=50), db: Session = Depends(get_db)) -> dict:
    clinic_id = _public_slug_clinic_id(db, clinic_slug)
    rows = db.execute(text("SELECT slug, title, excerpt, published_at FROM website_posts WHERE clinic_id = :c AND status = 'published' ORDER BY published_at DESC LIMIT :limit"), {"c": clinic_id, "limit": limit}).mappings().all() if clinic_id else []
    if clinic_id is None:
        raise _error("NOT_FOUND", "Website not found.", status.HTTP_404_NOT_FOUND)
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "cache_control": "public, max-age=60"}}


@public_router.get("/posts/{post_slug}")
def public_post(clinic_slug: str, post_slug: str, request: Request, db: Session = Depends(get_db)) -> dict:
    clinic_id = _public_slug_clinic_id(db, clinic_slug)
    row = db.execute(text("SELECT slug, title, excerpt, body, published_at, seo_title, seo_description FROM website_posts WHERE clinic_id = :c AND slug = :slug AND status = 'published'"), {"c": clinic_id, "slug": post_slug}).mappings().one_or_none() if clinic_id else None
    if row is None:
        raise _error("NOT_FOUND", "Post not found.", status.HTTP_404_NOT_FOUND)
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id, "cache_control": "public, max-age=60"}}


# ---------------------------------------------------------------- testimonials
_TESTIMONIAL_COLUMNS = "id, author_name, rating, body, source, consent_confirmed, status, moderated_at, version, created_at"


@router.get("/testimonials")
def testimonial_list(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "website.read")
    rows = db.execute(text(f"SELECT {_TESTIMONIAL_COLUMNS} FROM website_testimonials WHERE clinic_id = :c ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, created_at DESC LIMIT 200"), {"c": session["clinic_id"]}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.post("/testimonials", status_code=status.HTTP_201_CREATED)
def testimonial_create(payload: TestimonialCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write(request, db, session_token, csrf_token)
    if not payload.consent_confirmed:
        raise _error("CONSENT_REQUIRED", "Confirm the author consented to publishing this testimonial.", status.HTTP_400_BAD_REQUEST)
    row = db.execute(text(f"INSERT INTO website_testimonials (clinic_id, author_name, rating, body, consent_confirmed) VALUES (:c, :author_name, :rating, :body, true) RETURNING {_TESTIMONIAL_COLUMNS}"), {"c": session["clinic_id"], **payload.model_dump(exclude={"consent_confirmed"})}).mappings().one()
    _audit(db, session, request, "website.testimonial.create", "website_testimonial", row["id"])
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.post("/testimonials/{testimonial_id}/moderate")
def testimonial_moderate(testimonial_id: UUID, payload: TestimonialModerate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write(request, db, session_token, csrf_token, "website.publish")
    row = db.execute(text(f"""
        UPDATE website_testimonials SET status = :status, moderated_by = :user, moderated_at = now(), version = version + 1
        WHERE clinic_id = :c AND id = :id AND version = :v AND (:status <> 'approved' OR consent_confirmed)
        RETURNING {_TESTIMONIAL_COLUMNS}
    """), {"c": session["clinic_id"], "id": testimonial_id, "v": payload.expected_version, "status": payload.status, "user": session["user_id"]}).mappings().one_or_none()
    if row is None:
        raise _error("VERSION_CONFLICT", "The testimonial changed, does not exist, or lacks recorded consent.", status.HTTP_409_CONFLICT)
    _audit(db, session, request, f"website.testimonial.{payload.status}", "website_testimonial", testimonial_id)
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@public_router.get("/testimonials")
def public_testimonials(clinic_slug: str, request: Request, db: Session = Depends(get_db)) -> dict:
    clinic_id = _public_slug_clinic_id(db, clinic_slug)
    if clinic_id is None:
        raise _error("NOT_FOUND", "Website not found.", status.HTTP_404_NOT_FOUND)
    rows = db.execute(text("SELECT author_name AS title, rating, body AS quote FROM website_testimonials WHERE clinic_id = :c AND status = 'approved' ORDER BY moderated_at DESC LIMIT 30"), {"c": clinic_id}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id, "cache_control": "public, max-age=60"}}
