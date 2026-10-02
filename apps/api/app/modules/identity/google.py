"""Google sign-in (OAuth 2.0 authorization code + PKCE) for already-provisioned users.

It never creates accounts: staff are invited, and the verified Google email must match an
active user. MFA policy is identical to password sign-in because the session is created by
the same code path. The feature is off until GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET are set.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import APIRouter, Cookie, Depends, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.db.tenant import set_tenant_context
from app.modules.audit.service import record_event
from app.modules.identity.routes import _error, _set_session_cookies
from app.modules.identity.service import AuthenticationError, authenticate_external

router = APIRouter(prefix="/api/v1/auth/google", tags=["auth"])

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
FLOW_COOKIE = "google_oauth"
FLOW_TTL_SECONDS = 600


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def build_authorization_url(settings: Settings, state: str, verifier: str) -> str:
    query = urlencode({
        "client_id": settings.google_client_id, "redirect_uri": settings.google_callback_url, "response_type": "code",
        "scope": "openid email", "state": state, "code_challenge": pkce_challenge(verifier), "code_challenge_method": "S256",
        "prompt": "select_account", "access_type": "online",
    })
    return f"{AUTH_URL}?{query}"


def flow_cookie_matches(cookie: str | None, state: str) -> str | None:
    """Return the PKCE verifier when the cookie holds the same state the callback received."""
    if not cookie or "." not in cookie:
        return None
    stored_state, verifier = cookie.split(".", 1)
    return verifier if hmac.compare_digest(stored_state, state) and len(verifier) >= 43 else None


def _login_redirect(outcome: str) -> RedirectResponse:
    base = get_settings().public_app_url.rstrip("/")
    response = RedirectResponse(f"{base}/login?google={outcome}", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(FLOW_COOKIE, path="/api/v1/auth/google")
    return response


@router.get("/config")
def google_config(request: Request) -> dict:
    return {"data": {"enabled": get_settings().google_enabled}, "meta": {"request_id": request.state.request_id}}


@router.get("/start")
def google_start() -> RedirectResponse:
    settings = get_settings()
    if not settings.google_enabled:
        raise _error("NOT_FOUND", "Google sign-in is not enabled.", status.HTTP_404_NOT_FOUND)
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    response = RedirectResponse(build_authorization_url(settings, state, verifier), status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(FLOW_COOKIE, f"{state}.{verifier}", max_age=FLOW_TTL_SECONDS, httponly=True, secure=settings.app_env in {"staging", "production"}, samesite="lax", path="/api/v1/auth/google")
    return response


@router.get("/callback")
def google_callback(request: Request, code: str | None = Query(default=None, max_length=2048), state: str | None = Query(default=None, max_length=256), error: str | None = Query(default=None, max_length=100), flow: str | None = Cookie(default=None, alias=FLOW_COOKIE), db: Session = Depends(get_db)) -> RedirectResponse:
    settings = get_settings()
    if not settings.google_enabled:
        raise _error("NOT_FOUND", "Google sign-in is not enabled.", status.HTTP_404_NOT_FOUND)
    verifier = flow_cookie_matches(flow, state or "")
    if error or not code or verifier is None:
        return _login_redirect("error")
    try:
        with httpx.Client(timeout=10.0) as client:
            token = client.post(TOKEN_URL, data={"code": code, "client_id": settings.google_client_id, "client_secret": settings.google_client_secret, "redirect_uri": settings.google_callback_url, "grant_type": "authorization_code", "code_verifier": verifier})
            token.raise_for_status()
            info = client.get(USERINFO_URL, headers={"Authorization": f"Bearer {token.json()['access_token']}"})
            info.raise_for_status()
            profile = info.json()
    except (httpx.HTTPError, KeyError, ValueError):
        return _login_redirect("error")
    email = profile.get("email")
    if not isinstance(email, str) or profile.get("email_verified") is not True:
        return _login_redirect("unverified")
    try:
        result = authenticate_external(db, email, request.client.host if request.client else "unknown", request.headers.get("user-agent"))
    except AuthenticationError:
        db.rollback()
        return _login_redirect("no_account")
    if result.clinic_id is not None:
        set_tenant_context(db, result.clinic_id, result.user_id)
        record_event(db, clinic_id=result.clinic_id, actor_user_id=result.user_id, action="auth.login.google", entity_type="session", entity_id=None, outcome="success", request_id=UUID(request.state.request_id))
    outcome = "enroll" if result.mfa_enrollment_required else "mfa" if result.mfa_required else "ok"
    response = _login_redirect(outcome)
    _set_session_cookies(response, result.session_token, result.csrf_token, result.clinic_id)
    db.commit()
    return response
