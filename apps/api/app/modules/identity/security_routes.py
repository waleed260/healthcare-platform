"""Self-service account security: MFA management and signed-in device sessions (blueprint §5.1, §14.3)."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decrypt_field, generate_recovery_codes, hash_recovery_code, verify_totp
from app.db.session import get_db
from app.db.tenant import set_tenant_context
from app.modules.audit.service import record_event
from app.modules.identity.routes import _error, _session_or_401, _validate_origin
from app.modules.identity.schemas import MfaVerifyRequest
from app.modules.identity.service import SessionError, verify_csrf

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _write_session(request: Request, db: Session, session_token: str | None, csrf_token: str | None) -> dict:
    _validate_origin(request)
    session = _session_or_401(db, session_token)
    if not csrf_token:
        raise _error("CSRF_REQUIRED", "A CSRF token is required.", status.HTTP_403_FORBIDDEN)
    try:
        verify_csrf(session, csrf_token)
    except SessionError as exc:
        raise _error("CSRF_INVALID", "The CSRF token is invalid.", status.HTTP_403_FORBIDDEN) from exc
    return session


def _mfa_state(db: Session, session: dict) -> dict:
    return dict(db.execute(text("""
        SELECT EXISTS (SELECT 1 FROM mfa_methods WHERE user_id = :user_id AND enrolled_at IS NOT NULL) AS enrolled,
               (EXISTS (SELECT 1 FROM user_roles ur JOIN roles r ON r.id = ur.role_id WHERE ur.clinic_id = :clinic_id AND ur.user_id = :user_id AND r.name = 'owner')
                OR CAST(:clinic_id AS uuid) IS NULL) AS mandatory,
               (SELECT COUNT(*) FROM recovery_codes WHERE user_id = :user_id AND used_at IS NULL) AS recovery_codes_remaining
    """), {"user_id": session["user_id"], "clinic_id": session["clinic_id"]}).mappings().one())


def _audit(db: Session, session: dict, request: Request, action: str) -> None:
    if session["clinic_id"] is not None:
        set_tenant_context(db, session["clinic_id"], session["user_id"])
        record_event(db, clinic_id=session["clinic_id"], actor_user_id=session["user_id"], action=action, entity_type="user", entity_id=session["user_id"], outcome="success", request_id=UUID(request.state.request_id))


def _verified_secret(db: Session, session: dict, code: str) -> None:
    secret = db.execute(text("SELECT secret_ciphertext FROM mfa_methods WHERE user_id = :user_id AND enrolled_at IS NOT NULL AND method = 'totp'"), {"user_id": session["user_id"]}).scalar_one_or_none()
    if not secret or not verify_totp(decrypt_field(secret), code):
        raise _error("MFA_INVALID", "The MFA code is invalid.", status.HTTP_401_UNAUTHORIZED)


@router.get("/security")
def security_overview(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session")) -> dict:
    session = _session_or_401(db, session_token)
    sessions = db.execute(text("""
        SELECT id, user_agent, created_at, last_seen_at, (id = :current) AS current
        FROM sessions WHERE user_id = :user_id AND revoked_at IS NULL AND idle_expires_at > now() AND absolute_expires_at > now()
        ORDER BY last_seen_at DESC LIMIT 25
    """), {"user_id": session["user_id"], "current": session["id"]}).mappings().all()
    state = _mfa_state(db, session)
    db.commit()
    return {"data": {"mfa": {"enrolled": state["enrolled"], "mandatory": state["mandatory"], "recovery_codes_remaining": state["recovery_codes_remaining"]}, "sessions": [dict(row) for row in sessions], "google_sign_in": get_settings().google_enabled}, "meta": {"request_id": request.state.request_id}}


@router.post("/mfa/recovery-codes/regenerate")
def regenerate_recovery_codes(payload: MfaVerifyRequest, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_session(request, db, session_token, csrf_token)
    _verified_secret(db, session, payload.code)
    codes = generate_recovery_codes()
    db.execute(text("DELETE FROM recovery_codes WHERE user_id = :user_id"), {"user_id": session["user_id"]})
    db.execute(text("INSERT INTO recovery_codes (user_id, code_hash) VALUES (:user_id, :code_hash)"), [{"user_id": session["user_id"], "code_hash": hash_recovery_code(code)} for code in codes])
    _audit(db, session, request, "auth.mfa_recovery_regenerate")
    db.commit()
    return {"data": {"recovery_codes": codes}, "meta": {"request_id": request.state.request_id}}


@router.post("/mfa/disable")
def disable_mfa(payload: MfaVerifyRequest, request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_session(request, db, session_token, csrf_token)
    if _mfa_state(db, session)["mandatory"]:
        raise _error("MFA_MANDATORY", "MFA is required for owners and platform administrators and cannot be turned off.", status.HTTP_403_FORBIDDEN)
    _verified_secret(db, session, payload.code)
    db.execute(text("DELETE FROM recovery_codes WHERE user_id = :user_id"), {"user_id": session["user_id"]})
    db.execute(text("DELETE FROM mfa_methods WHERE user_id = :user_id"), {"user_id": session["user_id"]})
    _audit(db, session, request, "auth.mfa_disable")
    db.commit()
    return {"data": {"disabled": True}, "meta": {"request_id": request.state.request_id}}


@router.post("/sessions/revoke-others")
def revoke_other_sessions(request: Request, db: Session = Depends(get_db), session_token: str | None = Cookie(default=None, alias="healthcare_session"), csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
    session = _write_session(request, db, session_token, csrf_token)
    revoked = db.execute(text("UPDATE sessions SET revoked_at = now() WHERE user_id = :user_id AND id <> :current AND revoked_at IS NULL"), {"user_id": session["user_id"], "current": session["id"]}).rowcount
    _audit(db, session, request, "auth.sessions_revoke_others")
    db.commit()
    return {"data": {"revoked": revoked}, "meta": {"request_id": request.state.request_id}}
