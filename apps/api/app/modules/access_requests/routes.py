"""Self-service staff access requests.

Public: a person submits a request against a clinic *slug* (trusted server-side
resolution — they can never target a raw clinic id). A pending request grants no
access and creates no session. Admin: an authorized reviewer (staff.manage) for
that clinic lists, approves (issues a normal staff invitation with the chosen
role) or rejects requests. Tenant isolation is enforced by RLS on every query.
"""
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, Query, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.db.tenant import set_tenant_context
from app.modules.appointments.rate_limit import consume_public_management_limit
from app.modules.audit.service import record_event
from app.modules.identity.routes import _error
from app.modules.staff.routes import _authorized, _write_authorized
from app.modules.access_requests.schemas import AccessRequestApprove, AccessRequestCreate, AccessRequestReject
from app.modules.access_requests.service import (
    AccessRequestError,
    approve_access_request,
    reject_access_request,
    resolve_clinic_id,
    store_access_request,
)

public_router = APIRouter(prefix="/api/v1/public/access-requests", tags=["public-access-requests"])
admin_router = APIRouter(prefix="/api/v1/staff/access-requests", tags=["staff-access-requests"])

# Identical body for every public submit so the response never reveals whether the
# clinic exists, the email is already a member, or a duplicate request was collapsed.
_SUBMITTED = "Your request has been received. If it is valid, an administrator will review it."


@public_router.post("", status_code=status.HTTP_202_ACCEPTED)
def submit_access_request(payload: AccessRequestCreate, request: Request, db: Session = Depends(get_db)) -> dict:
    ip_address = request.client.host if request.client else "unknown"
    clinic_id = resolve_clinic_id(db, payload.clinic_slug)
    if clinic_id is not None:
        set_tenant_context(db, clinic_id)
        if not consume_public_management_limit(db, clinic_id=clinic_id, reference="public-access-request", ip_address=ip_address, maximum=5):
            raise _error("RATE_LIMITED", "Too many requests. Please try again later.", status.HTTP_429_TOO_MANY_REQUESTS)
        store_access_request(db, clinic_id, email=payload.email, display_name=payload.display_name,
                             requested_role=payload.requested_role, reason=payload.reason)
        db.commit()
    return {"data": {"status": "submitted", "message": _SUBMITTED}, "meta": {"request_id": request.state.request_id}}


@admin_router.get("")
def list_access_requests(request: Request, status_filter: str = Query(default="pending", alias="status", pattern="^(pending|approved|rejected|expired|revoked|all)$"), limit: int = Query(default=50, ge=1, le=100), db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "staff.manage")
    sql = ("SELECT id, normalized_email AS email, display_name, requested_role, reason, status, "
           "decided_at, created_at, version FROM access_requests WHERE clinic_id = :clinic_id")
    params: dict = {"clinic_id": session["clinic_id"], "limit": limit}
    if status_filter != "all":
        sql += " AND status = :status"
        params["status"] = status_filter
    sql += " ORDER BY created_at DESC LIMIT :limit"
    rows = db.execute(text(sql), params).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@admin_router.post("/{request_id}/approve", status_code=status.HTTP_201_CREATED)
def approve_request_endpoint(request_id: UUID, payload: AccessRequestApprove, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(request, db, session_token, "staff.manage", csrf_token)
    clinic_id = session["clinic_id"]
    try:
        token = approve_access_request(db, clinic_id, session["user_id"], request_id,
                                       role_name=payload.role_name, expected_version=payload.expected_version)
    except AccessRequestError as exc:
        raise _error(exc.code, exc.message, exc.http_status) from exc
    record_event(db, clinic_id=clinic_id, actor_user_id=session["user_id"], action="access_request.approve",
                 entity_type="access_request", entity_id=request_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    setup_url = f"{get_settings().public_app_url.rstrip('/')}/setup/staff?token={token}"
    return {"data": {"status": "approved", "setup_url": setup_url, "expires_in_seconds": 24 * 60 * 60}, "meta": {"request_id": request.state.request_id}}


@admin_router.post("/{request_id}/reject")
def reject_request_endpoint(request_id: UUID, payload: AccessRequestReject, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(request, db, session_token, "staff.manage", csrf_token)
    clinic_id = session["clinic_id"]
    try:
        reject_access_request(db, clinic_id, session["user_id"], request_id,
                              expected_version=payload.expected_version, note=payload.note)
    except AccessRequestError as exc:
        raise _error(exc.code, exc.message, exc.http_status) from exc
    record_event(db, clinic_id=clinic_id, actor_user_id=session["user_id"], action="access_request.reject",
                 entity_type="access_request", entity_id=request_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": {"status": "rejected"}, "meta": {"request_id": request.state.request_id}}
