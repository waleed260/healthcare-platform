from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, Request, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.audit.service import record_event
from app.modules.identity.routes import _error
from app.modules.websites.publishing import refresh_draft_snapshot
from app.modules.websites.routes import _authorized, _csrf
from app.modules.websites.schemas import RedirectCreate

router = APIRouter(prefix="/api/v1/websites/{website_id}/redirects", tags=["website-seo"])


@router.get("")
def redirect_list(website_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "website.read")
    rows = db.execute(text("SELECT id, from_path, to_path, status_code, created_at FROM website_redirects WHERE clinic_id = :clinic_id AND website_id = :website_id ORDER BY from_path LIMIT 500"), {"clinic_id": session["clinic_id"], "website_id": website_id}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.post("", status_code=status.HTTP_201_CREATED)
def redirect_create(website_id: UUID, payload: RedirectCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _authorized(db, session_token, "website.edit")
    _csrf(request, session, csrf_token)
    clinic_id = session["clinic_id"]
    reverse = db.execute(text("SELECT 1 FROM website_redirects WHERE clinic_id = :clinic_id AND website_id = :website_id AND from_path = :to_path AND to_path = :from_path"), {"clinic_id": clinic_id, "website_id": website_id, "to_path": payload.to_path, "from_path": payload.from_path}).scalar_one_or_none()
    if reverse is not None:
        raise _error("INVALID_INPUT", "That redirect would create a loop with an existing redirect.", status.HTTP_400_BAD_REQUEST)
    try:
        row = db.execute(text("""
            INSERT INTO website_redirects (clinic_id, website_id, from_path, to_path, status_code)
            SELECT :clinic_id, id, :from_path, :to_path, :status_code FROM websites WHERE clinic_id = :clinic_id AND id = :website_id AND archived_at IS NULL
            RETURNING id, from_path, to_path, status_code, created_at
        """), {"clinic_id": clinic_id, "website_id": website_id, **payload.model_dump()}).mappings().one_or_none()
    except IntegrityError as exc:
        db.rollback()
        raise _error("DUPLICATE", "A redirect for this path already exists.", status.HTTP_409_CONFLICT) from exc
    if row is None:
        raise _error("NOT_FOUND", "Website not found.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=clinic_id, actor_user_id=session["user_id"], action="website.redirect.create", entity_type="website_redirect", entity_id=row["id"], outcome="success", request_id=UUID(request.state.request_id))
    refresh_draft_snapshot(db, clinic_id, website_id, session["user_id"])
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.delete("/{redirect_id}")
def redirect_delete(website_id: UUID, redirect_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _authorized(db, session_token, "website.edit")
    _csrf(request, session, csrf_token)
    deleted = db.execute(text("DELETE FROM website_redirects WHERE clinic_id = :clinic_id AND website_id = :website_id AND id = :id"), {"clinic_id": session["clinic_id"], "website_id": website_id, "id": redirect_id}).rowcount
    if not deleted:
        raise _error("NOT_FOUND", "Redirect not found.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="website.redirect.delete", entity_type="website_redirect", entity_id=redirect_id, outcome="success", request_id=UUID(request.state.request_id))
    refresh_draft_snapshot(db, session["clinic_id"], website_id, session["user_id"])
    db.commit()
    return {"data": {"deleted": True}, "meta": {"request_id": request.state.request_id}}
