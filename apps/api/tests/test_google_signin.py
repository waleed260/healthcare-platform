import base64
import hashlib

from app.core.config import Settings
from app.main import app
from app.modules.identity.google import build_authorization_url, flow_cookie_matches, pkce_challenge


def test_pkce_challenge_matches_rfc7636_vector() -> None:
    assert pkce_challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk") == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_authorization_url_contains_pkce_and_state() -> None:
    settings = Settings(google_client_id="client-1", google_client_secret="secret", public_app_url="https://app.example")
    url = build_authorization_url(settings, "state123", "v" * 64)
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    for part in ("client_id=client-1", "state=state123", "code_challenge_method=S256", "scope=openid+email", "redirect_uri=https%3A%2F%2Fapp.example%2Fapi%2Fv1%2Fauth%2Fgoogle%2Fcallback"):
        assert part in url
    assert "secret" not in url


def test_flow_cookie_binds_state() -> None:
    verifier = "a" * 64
    assert flow_cookie_matches(f"abc.{verifier}", "abc") == verifier
    assert flow_cookie_matches(f"abc.{verifier}", "different") is None
    assert flow_cookie_matches(None, "abc") is None
    assert flow_cookie_matches("abc.short", "abc") is None
    assert flow_cookie_matches("nodot", "nodot") is None


def test_disabled_without_credentials_and_routes_registered() -> None:
    assert Settings(google_client_id="", google_client_secret="").google_enabled is False
    assert Settings(google_client_id="x", google_client_secret="y").google_enabled is True
    paths = set(app.openapi()["paths"])
    assert {"/api/v1/auth/google/config", "/api/v1/auth/google/start", "/api/v1/auth/google/callback"} <= paths
    assert base64 and hashlib


def test_account_security_routes_registered() -> None:
    paths = set(app.openapi()["paths"])
    assert {"/api/v1/auth/security", "/api/v1/auth/mfa/recovery-codes/regenerate", "/api/v1/auth/mfa/disable", "/api/v1/auth/sessions/revoke-others"} <= paths


def test_database_connect_timeout_is_bounded_and_overridable() -> None:
    import pytest
    from pydantic import ValidationError

    assert Settings().database_connect_timeout == 2
    assert Settings(database_connect_timeout=10).database_connect_timeout == 10
    for bad in (0, 61):
        with pytest.raises(ValidationError):
            Settings(database_connect_timeout=bad)
