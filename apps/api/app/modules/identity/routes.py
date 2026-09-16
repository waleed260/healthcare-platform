from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.tenant import set_tenant_context
from app.modules.audit.service import record_event
from app.db.session import get_db
from app.modules.identity.schemas import InvitationConsumeRequest, InvitationCreateRequest, LoginRequest, ManualResetConsumeRequest, MfaEnrollResponse, MfaRecoveryRequest, MfaVerifyRequest, SessionRevokeRequest
from app.modules.identity.service import (
    AuthenticationError,
    SessionError,
    TokenError,
    authenticate,
    begin_mfa_enrollment,
    complete_mfa,
    consume_manual_reset,
    consume_staff_invitation,
    create_staff_invitation,
    get_session,
    recover_mfa,
    revoke_session,
    verify_csrf,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _error(code: str, message: str, status_code: int, fields: object | None = None) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": {"code": code, "message": message, "fields": fields}})


def _set_session_cookies(response: Response, session_token: str, csrf_token: str, clinic_id: UUID | None = None) -> None:
    settings = get_settings()
    secure = settings.app_env == "production"
    max_age = 60 * 60 * 24 if clinic_id is None else 60 * 60 * 24 * 7
    common = {"secure": secure, "httponly": True, "samesite": "lax", "path": "/", "max_age": max_age}
    if settings.cookie_domain:
        common["domain"] = settings.cookie_domain
    response.set_cookie(settings.session_cookie_name, session_token, **common)
    response.set_cookie("csrf_token", csrf_token, secure=secure, httponly=False, samesite="lax", path="/", max_age=max_age, domain=settings.cookie_domain or None)


def _clear_session_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name, domain=settings.cookie_domain or None, path="/")
    response.delete_cookie("csrf_token", domain=settings.cookie_domain or None, path="/")


def _validate_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin or origin not in get_settings().allowed_origins:
        raise _error("CSRF_ORIGIN_REJECTED", "The request origin is not allowed.", status.HTTP_403_FORBIDDEN)


def _session_or_401(db: Session, session_token: str | None, require_mfa: bool = True) -> dict:
    if not session_token:
        raise _error("SESSION_EXPIRED", "Your session has expired.", status.HTTP_401_UNAUTHORIZED)
    try:
        session = get_session(db, session_token)
    except SessionError as exc:
        raise _error(exc.code, "Your session has expired.", status.HTTP_401_UNAUTHORIZED) from exc
    if require_mfa and not session["mfa_verified"]:
        raise _error("MFA_REQUIRED", "Complete MFA before continuing.", status.HTTP_401_UNAUTHORIZED)
    return session


@router.post("/login")
def login(payload: LoginRequest, response: Response, request: Request, db: Session = Depends(get_db)) -> dict:
    try:
        result = authenticate(db, payload.email, payload.password, request.client.host if request.client else "unknown", request.headers.get("user-agent"))
        if result.clinic_id is not None:
            set_tenant_context(db, result.clinic_id, result.user_id)
            record_event(db, clinic_id=result.clinic_id, actor_user_id=result.user_id, action="auth.login", entity_type="session", entity_id=None, outcome="success", request_id=UUID(request.state.request_id))
        _set_session_cookies(response, result.session_token, result.csrf_token, result.clinic_id)
        db.commit()
        return {"data": {"mfa_required": result.mfa_required, "user_id": result.user_id, "display_name": result.display_name}, "meta": {"request_id": request.state.request_id}}
    except AuthenticationError as exc:
        db.rollback()
        raise _error(exc.code, "The email or password is not correct.", status.HTTP_401_UNAUTHORIZED) from exc


@router.post("/logout")
def logout(response: Response, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    _validate_origin(request)
    session = _session_or_401(db, session_token, require_mfa=False)
    if not csrf_token:
        raise _error("CSRF_REQUIRED", "A CSRF token is required.", status.HTTP_403_FORBIDDEN)
    try:
        verify_csrf(session, csrf_token)
    except SessionError as exc:
        raise _error("CSRF_INVALID", "The CSRF token is invalid.", status.HTTP_403_FORBIDDEN) from exc
    revoke_session(db, session_token or "")
    if session["clinic_id"] is not None:
        set_tenant_context(db, session["clinic_id"], session["user_id"])
        record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="auth.logout", entity_type="session", entity_id=None, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    _clear_session_cookies(response)
    return {"data": {"logged_out": True}, "meta": {"request_id": request.state.request_id}}


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _session_or_401(db, session_token)
    return {"data": {"user_id": session["user_id"], "clinic_id": session["clinic_id"], "display_name": session["display_name"], "email": session["normalized_email"]}, "meta": {"request_id": request.state.request_id}}


@router.post("/sessions/revoke")
def sessions_revoke(payload: SessionRevokeRequest, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    _validate_origin(request)
    session = _session_or_401(db, session_token)
    if not csrf_token:
        raise _error("CSRF_REQUIRED", "A CSRF token is required.", status.HTTP_403_FORBIDDEN)
    try:
        verify_csrf(session, csrf_token)
    except SessionError as exc:
        raise _error("CSRF_INVALID", "The CSRF token is invalid.", status.HTTP_403_FORBIDDEN) from exc
    revoked = db.execute(text("""
        UPDATE sessions SET revoked_at = now()
        WHERE id = :session_id AND user_id = :user_id AND revoked_at IS NULL
        RETURNING id, revoked_at
    """), {"session_id": payload.session_id, "user_id": session["user_id"]}).mappings().one_or_none()
    if revoked is None:
        raise _error("NOT_FOUND", "Session not found or already revoked.", status.HTTP_404_NOT_FOUND)
    if session["clinic_id"] is not None:
        set_tenant_context(db, session["clinic_id"], session["user_id"])
        record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="auth.session_revoke", entity_type="session", entity_id=payload.session_id, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return {"data": {"session_id": revoked["id"], "revoked": True}, "meta": {"request_id": request.state.request_id}}


@router.post("/manual-reset/consume")
def manual_reset_consume(payload: ManualResetConsumeRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    try:
        user_id = consume_manual_reset(db, payload.token, payload.new_password)
        clinic_id = db.execute(text("SELECT clinic_id FROM users WHERE id = :user_id"), {"user_id": user_id}).scalar_one_or_none()
        if clinic_id is not None:
            set_tenant_context(db, clinic_id, user_id)
            record_event(db, clinic_id=clinic_id, actor_user_id=user_id, action="auth.password_reset", entity_type="user", entity_id=user_id, outcome="success", request_id=UUID(request.state.request_id))
        db.commit()
        return {"data": {"reset": True}, "meta": {"request_id": request.state.request_id}}
    except (TokenError, AuthenticationError) as exc:
        db.rollback()
        raise _error(exc.code, "The reset link is invalid or expired.", status.HTTP_400_BAD_REQUEST) from exc


@router.post("/mfa/enroll", response_model=MfaEnrollResponse)
def mfa_enroll(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> MfaEnrollResponse:
    _validate_origin(request)
    session = _session_or_401(db, session_token, require_mfa=False)
    if not csrf_token:
        raise _error("CSRF_REQUIRED", "A CSRF token is required.", status.HTTP_403_FORBIDDEN)
    try:
        verify_csrf(session, csrf_token)
    except SessionError as exc:
        raise _error("CSRF_INVALID", "The CSRF token is invalid.", status.HTTP_403_FORBIDDEN) from exc
    secret, codes = begin_mfa_enrollment(db, session["user_id"])
    if session["clinic_id"] is not None:
        set_tenant_context(db, session["clinic_id"], session["user_id"])
        record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="auth.mfa_enroll", entity_type="mfa_method", entity_id=None, outcome="success", request_id=UUID(request.state.request_id))
    db.commit()
    return MfaEnrollResponse(secret=secret, recovery_codes=codes)


@router.post("/mfa/verify")
def mfa_verify(payload: MfaVerifyRequest, response: Response, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    _validate_origin(request)
    session = _session_or_401(db, session_token, require_mfa=False)
    if not csrf_token:
        raise _error("CSRF_REQUIRED", "A CSRF token is required.", status.HTTP_403_FORBIDDEN)
    try:
        verify_csrf(session, csrf_token)
        rotation = complete_mfa(db, session, payload.code)
        if session["clinic_id"] is not None:
            set_tenant_context(db, session["clinic_id"], session["user_id"])
            record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="auth.mfa_verify", entity_type="session", entity_id=None, outcome="success", request_id=UUID(request.state.request_id))
        db.commit()
        _set_session_cookies(response, rotation.session_token, rotation.csrf_token, session["clinic_id"])
    except (SessionError, AuthenticationError) as exc:
        db.rollback()
        raise _error("MFA_INVALID", "The MFA code is invalid.", status.HTTP_401_UNAUTHORIZED) from exc
    return {"data": {"verified": True}, "meta": {"request_id": request.state.request_id}}


@router.post("/mfa/recover")
def mfa_recover(payload: MfaRecoveryRequest, response: Response, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    _validate_origin(request)
    session = _session_or_401(db, session_token, require_mfa=False)
    if not csrf_token:
        raise _error("CSRF_REQUIRED", "A CSRF token is required.", status.HTTP_403_FORBIDDEN)
    try:
        verify_csrf(session, csrf_token)
        rotation = recover_mfa(db, session, payload.code)
        if session["clinic_id"] is not None:
            set_tenant_context(db, session["clinic_id"], session["user_id"])
            record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action="auth.mfa_recover", entity_type="session", entity_id=None, outcome="success", request_id=UUID(request.state.request_id))
        db.commit()
        _set_session_cookies(response, rotation.session_token, rotation.csrf_token, session["clinic_id"])
    except (SessionError, AuthenticationError) as exc:
        db.rollback()
        raise _error("MFA_INVALID", "The recovery code is invalid.", status.HTTP_401_UNAUTHORIZED) from exc
    return {"data": {"verified": True}, "meta": {"request_id": request.state.request_id}}


@router.post("/manual-invite/consume")
def manual_invite_consume(payload: InvitationConsumeRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    try:
        user_id = consume_staff_invitation(db, payload.token, payload.password, payload.display_name)
        clinic_id = db.execute(text("SELECT clinic_id FROM users WHERE id = :user_id"), {"user_id": user_id}).scalar_one_or_none()
        if clinic_id is not None:
            set_tenant_context(db, clinic_id, user_id)
            record_event(db, clinic_id=clinic_id, actor_user_id=user_id, action="auth.invitation_consume", entity_type="user", entity_id=user_id, outcome="success", request_id=UUID(request.state.request_id))
        db.commit()
        return {"data": {"user_id": user_id, "activated": True}, "meta": {"request_id": request.state.request_id}}
    except (TokenError, AuthenticationError) as exc:
        db.rollback()
        raise _error("INVALID_INVITATION", "The invitation is invalid, expired, or the password does not meet policy.", status.HTTP_400_BAD_REQUEST) from exc
