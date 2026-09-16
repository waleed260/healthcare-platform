from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, Request, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.db.tenant import set_tenant_context
from app.modules.authorization.service import ForbiddenError, require_permission
from app.modules.identity.routes import _error, _session_or_401, _validate_origin
from app.modules.identity.service import SessionError, create_staff_invitation, verify_csrf
from app.modules.audit.service import record_event
from app.modules.staff.schemas import BranchScopeCreate, RoleAssignment, StaffInvitationCreate, StaffStatusUpdate

router = APIRouter(prefix="/api/v1/staff", tags=["staff"])


def _revoke_user_sessions(db: Session, user_id: UUID) -> None:
    """Force re-authentication after a user's effective clinic privileges change."""
    db.execute(
        text("UPDATE sessions SET revoked_at = now() WHERE user_id = :user_id AND revoked_at IS NULL"),
        {"user_id": user_id},
    )


@router.get("/roles")
def role_list(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "staff.read")
    rows = db.execute(text("""
        SELECT r.id, r.name, r.is_system,
               COALESCE(jsonb_agg(jsonb_build_object('code', p.code) ORDER BY p.code) FILTER (WHERE p.code IS NOT NULL), '[]'::jsonb) AS permissions
        FROM roles r
        LEFT JOIN role_permissions rp ON rp.role_id = r.id
        LEFT JOIN permissions p ON p.id = rp.permission_id
        WHERE r.clinic_id IS NULL OR r.clinic_id = :clinic_id
        GROUP BY r.id, r.name, r.is_system ORDER BY r.name
    """), {"clinic_id": session["clinic_id"]}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.get("/permissions")
def permission_list(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "staff.read")
    rows = db.execute(text("SELECT code, description FROM permissions ORDER BY code")).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.post("/invitations", status_code=status.HTTP_201_CREATED)
def create_invitation(payload: StaffInvitationCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    _validate_origin(request)
    session = _session_or_401(db, session_token)
    if session["clinic_id"] is None:
        raise _error("FORBIDDEN", "A clinic context is required.", status.HTTP_403_FORBIDDEN)
    set_tenant_context(db, session["clinic_id"], session["user_id"])
    if not csrf_token:
        raise _error("CSRF_REQUIRED", "A CSRF token is required.", status.HTTP_403_FORBIDDEN)
    try:
        verify_csrf(session, csrf_token)
        require_permission(db, session["user_id"], session["clinic_id"], "staff.manage")
    except SessionError as exc:
        raise _error("CSRF_INVALID", "The CSRF token is invalid.", status.HTTP_403_FORBIDDEN) from exc
    except ForbiddenError as exc:
        raise _error("FORBIDDEN", "You do not have permission to invite staff.", status.HTTP_403_FORBIDDEN) from exc
    token = create_staff_invitation(db, session["clinic_id"], session["user_id"], payload.email)
    db.commit()
    setup_url = f"{get_settings().public_app_url.rstrip('/')}/setup/staff?token={token}"
    return {"data": {"setup_url": setup_url, "expires_in_seconds": 24 * 60 * 60}, "meta": {"request_id": request.state.request_id}}


def _authorized(db: Session, session_token: str | None, permission: str) -> dict:
    session = _session_or_401(db, session_token)
    if session["clinic_id"] is None:
        raise _error("FORBIDDEN", "A clinic context is required.", status.HTTP_403_FORBIDDEN)
    set_tenant_context(db, session["clinic_id"], session["user_id"])
    try:
        require_permission(db, session["user_id"], session["clinic_id"], permission)
    except ForbiddenError as exc:
        raise _error("FORBIDDEN", "You do not have permission for this operation.", status.HTTP_403_FORBIDDEN) from exc
    return session


def _write_authorized(db: Session, request: Request, session_token: str | None, permission: str, csrf_token: str | None) -> dict:
    _validate_origin(request)
    session = _authorized(db, session_token, permission)
    if not csrf_token:
        raise _error("CSRF_REQUIRED", "A CSRF token is required.", status.HTTP_403_FORBIDDEN)
    try:
        verify_csrf(session, csrf_token)
    except SessionError as exc:
        raise _error("CSRF_INVALID", "The CSRF token is invalid.", status.HTTP_403_FORBIDDEN) from exc
    return session


@router.get("/users")
def user_list(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "staff.read")
    rows = db.execute(text("""
        SELECT id, normalized_email, display_name, status, failed_login_count, last_login_at, version, created_at, updated_at
        FROM users WHERE clinic_id = :clinic_id AND archived_at IS NULL ORDER BY display_name, id
    """), {"clinic_id": session["clinic_id"]}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.get("/users/{user_id}")
def user_detail(user_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "staff.read")
    user = db.execute(text("""
        SELECT id, normalized_email, display_name, status, failed_login_count, last_login_at, version, created_at, updated_at
        FROM users WHERE clinic_id = :clinic_id AND id = :user_id AND archived_at IS NULL
    """), {"clinic_id": session["clinic_id"], "user_id": user_id}).mappings().one_or_none()
    if user is None:
        raise _error("NOT_FOUND", "Staff member not found.", status.HTTP_404_NOT_FOUND)
    roles = db.execute(text("""
        SELECT r.id, r.name, r.is_system
        FROM user_roles ur JOIN roles r ON r.id = ur.role_id
        WHERE ur.clinic_id = :clinic_id AND ur.user_id = :user_id ORDER BY r.name
    """), {"clinic_id": session["clinic_id"], "user_id": user_id}).mappings().all()
    scopes = db.execute(text("""
        SELECT b.id AS branch_id, b.code, b.name
        FROM user_branch_scopes s JOIN branches b ON b.clinic_id = s.clinic_id AND b.id = s.branch_id
        WHERE s.clinic_id = :clinic_id AND s.user_id = :user_id ORDER BY b.name
    """), {"clinic_id": session["clinic_id"], "user_id": user_id}).mappings().all()
    db.commit()
    return {"data": {**dict(user), "roles": [dict(row) for row in roles], "branch_scopes": [dict(row) for row in scopes]}, "meta": {"request_id": request.state.request_id}}


@router.post("/users/{user_id}/status")
def user_status(user_id: UUID, payload: StaffStatusUpdate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "staff.manage", csrf_token)
    if user_id == session["user_id"] and payload.status != "active":
        raise _error("INVALID_INPUT", "You cannot deactivate your own current account.", status.HTTP_400_BAD_REQUEST)
    row = db.execute(text("""
        UPDATE users SET status = :status, version = version + 1, updated_at = now()
        WHERE clinic_id = :clinic_id AND id = :user_id AND archived_at IS NULL AND version = :expected_version
        RETURNING id, status, version, updated_at
    """), {"clinic_id": session["clinic_id"], "user_id": user_id, "status": payload.status, "expected_version": payload.expected_version}).mappings().one_or_none()
    if row is None:
        raise _error("VERSION_CONFLICT", "The staff record changed before this command.", status.HTTP_409_CONFLICT)
    if payload.status != "active":
        db.execute(text("UPDATE sessions SET revoked_at = now() WHERE user_id = :user_id AND revoked_at IS NULL"), {"user_id": user_id})
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="staff.status_change", entity_type="user", entity_id=user_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"status": payload.status})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.delete("/invitations/{invitation_id}")
def invitation_revoke(invitation_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "staff.manage", csrf_token)
    row = db.execute(text("UPDATE staff_invitations SET revoked_at = now() WHERE clinic_id = :clinic_id AND id = :id AND consumed_at IS NULL AND revoked_at IS NULL RETURNING id, revoked_at"), {"clinic_id": session["clinic_id"], "id": invitation_id}).mappings().one_or_none()
    if row is None:
        raise _error("NOT_FOUND", "Invitation not found or already closed.", status.HTTP_404_NOT_FOUND)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="staff.invitation_revoke", entity_type="staff_invitation", entity_id=invitation_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.get("/users/{user_id}/roles")
def user_roles(user_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "staff.read")
    rows = db.execute(text("""
        SELECT r.id, r.name, r.is_system FROM user_roles ur JOIN roles r ON r.id = ur.role_id
        WHERE ur.clinic_id = :clinic_id AND ur.user_id = :user_id ORDER BY r.name
    """), {"clinic_id": session["clinic_id"], "user_id": user_id}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.post("/users/{user_id}/roles", status_code=status.HTTP_201_CREATED)
def user_role_add(user_id: UUID, payload: RoleAssignment, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "staff.manage", csrf_token)
    try:
        inserted = db.execute(text("""
            INSERT INTO user_roles (clinic_id, user_id, role_id, assigned_by)
            SELECT :clinic_id, u.id, r.id, :actor
            FROM users u CROSS JOIN roles r
            WHERE u.id = :user_id AND u.clinic_id = :clinic_id
              AND u.status = 'active' AND u.archived_at IS NULL
              AND r.id = :role_id AND (r.clinic_id = :clinic_id OR r.clinic_id IS NULL)
            RETURNING role_id
        """), {"clinic_id": session["clinic_id"], "user_id": user_id, "role_id": payload.role_id, "actor": session["user_id"]}).scalar_one_or_none()
        if inserted is None:
            raise IntegrityError("role not found", params=None, orig=None)
    except IntegrityError as exc:
        db.rollback()
        raise _error("NOT_FOUND", "User or role not found, or role already assigned.", status.HTTP_409_CONFLICT) from exc
    _revoke_user_sessions(db, user_id)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="staff.role_assign", entity_type="user_role", entity_id=user_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"role_id": str(payload.role_id)})
    db.commit()
    return {"data": {"user_id": user_id, "role_id": payload.role_id, "assigned": True}, "meta": {"request_id": request.state.request_id}}


@router.delete("/users/{user_id}/roles/{role_id}")
def user_role_remove(user_id: UUID, role_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "staff.manage", csrf_token)
    deleted = db.execute(text("DELETE FROM user_roles WHERE clinic_id = :clinic_id AND user_id = :user_id AND role_id = :role_id RETURNING role_id"), {"clinic_id": session["clinic_id"], "user_id": user_id, "role_id": role_id}).scalar_one_or_none()
    if deleted is None:
        raise _error("NOT_FOUND", "Role assignment not found.", status.HTTP_404_NOT_FOUND)
    _revoke_user_sessions(db, user_id)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="staff.role_remove", entity_type="user_role", entity_id=user_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"role_id": str(role_id)})
    db.commit()
    return {"data": {"user_id": user_id, "role_id": role_id, "assigned": False}, "meta": {"request_id": request.state.request_id}}


@router.get("/users/{user_id}/branch-scopes")
def branch_scope_list(user_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _authorized(db, session_token, "staff.read")
    rows = db.execute(text("SELECT branch_id, created_at FROM user_branch_scopes WHERE clinic_id = :clinic_id AND user_id = :user_id ORDER BY branch_id"), {"clinic_id": session["clinic_id"], "user_id": user_id}).mappings().all()
    db.commit()
    return {"data": [dict(row) for row in rows], "meta": {"request_id": request.state.request_id}}


@router.post("/users/{user_id}/branch-scopes", status_code=status.HTTP_201_CREATED)
def branch_scope_add(user_id: UUID, payload: BranchScopeCreate, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "staff.manage", csrf_token)
    try:
        row = db.execute(text("""
            INSERT INTO user_branch_scopes (clinic_id, user_id, branch_id)
            SELECT :clinic_id, u.id, b.id
            FROM users u CROSS JOIN branches b
            WHERE u.id = :user_id AND u.clinic_id = :clinic_id
              AND u.status = 'active' AND u.archived_at IS NULL
              AND b.id = :branch_id AND b.clinic_id = :clinic_id
              AND b.status = 'active' AND b.archived_at IS NULL
            RETURNING branch_id, created_at
        """), {"clinic_id": session["clinic_id"], "user_id": user_id, "branch_id": payload.branch_id}).mappings().one_or_none()
        if row is None:
            raise IntegrityError("user or branch is inactive or not found", params=None, orig=None)
    except IntegrityError as exc:
        db.rollback()
        raise _error("NOT_FOUND", "User or branch not found, or scope already exists.", status.HTTP_409_CONFLICT) from exc
    _revoke_user_sessions(db, user_id)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="staff.branch_scope_add", entity_type="user_branch_scope", entity_id=user_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"branch_id": str(payload.branch_id)})
    db.commit()
    return {"data": dict(row), "meta": {"request_id": request.state.request_id}}


@router.delete("/users/{user_id}/branch-scopes/{branch_id}")
def branch_scope_remove(user_id: UUID, branch_id: UUID, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_authorized(db, request, session_token, "staff.manage", csrf_token)
    deleted = db.execute(text("DELETE FROM user_branch_scopes WHERE clinic_id = :clinic_id AND user_id = :user_id AND branch_id = :branch_id RETURNING branch_id"), {"clinic_id": session["clinic_id"], "user_id": user_id, "branch_id": branch_id}).scalar_one_or_none()
    if deleted is None:
        raise _error("NOT_FOUND", "Branch scope not found.", status.HTTP_404_NOT_FOUND)
    _revoke_user_sessions(db, user_id)
    record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="staff.branch_scope_remove", entity_type="user_branch_scope", entity_id=user_id, outcome="success", request_id=UUID(request.state.request_id), metadata={"branch_id": str(branch_id)})
    db.commit()
    return {"data": {"user_id": user_id, "branch_id": branch_id, "scoped": False}, "meta": {"request_id": request.state.request_id}}
