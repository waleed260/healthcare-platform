from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.tenant import set_tenant_context
from app.core.security import (
    encrypt_field,
    generate_recovery_codes,
    generate_totp_secret,
    hash_ip,
    hash_recovery_code,
    hash_token,
    hash_password,
    new_csrf_token,
    new_opaque_token,
    utc_now,
    verify_password,
    verify_totp,
)


class AuthenticationError(RuntimeError):
    code = "INVALID_CREDENTIALS"


class SessionError(RuntimeError):
    code = "SESSION_EXPIRED"


class TokenError(RuntimeError):
    code = "INVALID_TOKEN"


def _validate_password_policy(password: str) -> None:
    if len(password) < 12 or password.lower() == password or password.upper() == password or not any(char.isdigit() for char in password):
        raise AuthenticationError()


@dataclass(frozen=True)
class LoginResult:
    session_token: str
    csrf_token: str
    user_id: UUID
    clinic_id: UUID | None
    display_name: str
    mfa_required: bool
    mfa_enrollment_required: bool


@dataclass(frozen=True)
class SessionRotation:
    session_token: str
    csrf_token: str


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def _record_failure(db: Session, bucket_key: str) -> None:
    now = utc_now()
    db.execute(
        text("""
            INSERT INTO auth_rate_limit_buckets (bucket_key, failure_count, first_failure_at, updated_at)
            VALUES (:bucket_key, 1, :now, :now)
            ON CONFLICT (bucket_key) DO UPDATE SET
                failure_count = auth_rate_limit_buckets.failure_count + 1,
                locked_until = CASE
                    WHEN auth_rate_limit_buckets.failure_count + 1 >= 5 THEN :locked_until
                    ELSE auth_rate_limit_buckets.locked_until
                END,
                updated_at = :now
        """),
        {"bucket_key": bucket_key, "now": now, "locked_until": now + timedelta(minutes=15)},
    )


def _is_locked(db: Session, bucket_key: str) -> bool:
    locked_until = db.execute(
        text("SELECT locked_until FROM auth_rate_limit_buckets WHERE bucket_key = :bucket_key"),
        {"bucket_key": bucket_key},
    ).scalar_one_or_none()
    return locked_until is not None and locked_until > utc_now()


def _clear_failure(db: Session, bucket_key: str) -> None:
    db.execute(text("DELETE FROM auth_rate_limit_buckets WHERE bucket_key = :bucket_key"), {"bucket_key": bucket_key})


def authenticate(db: Session, email: str, password: str, ip_address: str, user_agent: str | None) -> LoginResult:
    normalized_email = normalize_email(email)
    bucket_key = hash_token(f"account:{normalized_email}:ip:{ip_address}")
    if _is_locked(db, bucket_key):
        raise AuthenticationError()
    user = db.execute(
        text("""
            SELECT u.id, u.clinic_id, u.display_name, u.password_hash, u.status
            FROM users u
            LEFT JOIN clinics c ON c.id = u.clinic_id
            WHERE u.normalized_email = :email
              AND u.status = 'active'
              AND (u.clinic_id IS NULL OR (c.status = 'active' AND c.archived_at IS NULL))
        """),
        {"email": normalized_email},
    ).mappings().one_or_none()
    if user is None or not verify_password(user["password_hash"], password):
        _record_failure(db, bucket_key)
        raise AuthenticationError()

    _clear_failure(db, bucket_key)
    now = utc_now()
    # Owner/MFA role discovery is tenant-scoped under forced RLS. Establish the
    # context only after the password has been verified and the user/clinic
    # relationship has been resolved above.
    if user["clinic_id"] is not None:
        set_tenant_context(db, user["clinic_id"], user["id"])
    session_token = new_opaque_token()
    csrf_token = new_csrf_token()
    mfa_state = db.execute(
        text("""
            SELECT EXISTS (
                SELECT 1 FROM mfa_methods
                WHERE user_id = :user_id AND enrolled_at IS NOT NULL
            ) AS mfa_enrolled, EXISTS (
                SELECT 1
                FROM user_roles ur
                JOIN roles r ON r.id = ur.role_id
                WHERE ur.clinic_id = :clinic_id AND ur.user_id = :user_id AND r.name = 'owner'
            ) OR (:clinic_id IS NULL) AS mfa_mandatory
        """),
        {"user_id": user["id"], "clinic_id": user["clinic_id"]},
    ).mappings().one()
    mfa_enrollment_required = bool(mfa_state["mfa_mandatory"] and not mfa_state["mfa_enrolled"])
    mfa_required = bool(mfa_state["mfa_mandatory"] or mfa_state["mfa_enrolled"])
    idle_duration = timedelta(minutes=30) if user["clinic_id"] is None else timedelta(hours=8)
    absolute_duration = timedelta(hours=24) if user["clinic_id"] is None else timedelta(days=7)
    db.execute(
        text("""
            INSERT INTO sessions
              (user_id, token_hash, csrf_token_hash, mfa_verified, ip_hash, user_agent,
               idle_expires_at, absolute_expires_at)
            VALUES (:user_id, :token_hash, :csrf_hash, :mfa_verified, :ip_hash, :user_agent,
                    :idle_expires_at, :absolute_expires_at)
        """),
        {
            "user_id": user["id"],
            "token_hash": hash_token(session_token),
            "csrf_hash": hash_token(csrf_token),
            "mfa_verified": not mfa_required,
            "ip_hash": hash_ip(ip_address),
            "user_agent": user_agent,
            "idle_expires_at": now + idle_duration,
            "absolute_expires_at": now + absolute_duration,
        },
    )
    db.execute(text("UPDATE users SET failed_login_count = 0, last_login_at = :now WHERE id = :id"), {"id": user["id"], "now": now})
    return LoginResult(session_token, csrf_token, user["id"], user["clinic_id"], user["display_name"], mfa_required, mfa_enrollment_required)


def revoke_session(db: Session, session_token: str) -> None:
    db.execute(text("UPDATE sessions SET revoked_at = :now WHERE token_hash = :token_hash"), {"now": utc_now(), "token_hash": hash_token(session_token)})


def get_session(db: Session, session_token: str) -> dict:
    session = db.execute(
        text("""
            SELECT s.id, s.user_id, s.csrf_token_hash, s.mfa_verified, s.idle_expires_at,
                   s.absolute_expires_at, s.ip_hash, s.user_agent, s.support_access_id,
                   u.is_platform_admin, COALESCE(u.clinic_id, support.clinic_id) AS clinic_id,
                   u.display_name, u.normalized_email
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            LEFT JOIN clinics c ON c.id = u.clinic_id
            LEFT JOIN support_access_sessions support ON support.id = s.support_access_id
            WHERE s.token_hash = :token_hash AND s.revoked_at IS NULL
              AND u.status = 'active'
              AND (u.clinic_id IS NULL OR (c.status = 'active' AND c.archived_at IS NULL))
              AND (
                  s.support_access_id IS NULL
                  OR (u.is_platform_admin AND support.revoked_at IS NULL AND support.starts_at <= now() AND support.expires_at > now())
              )
        """),
        {"token_hash": hash_token(session_token)},
    ).mappings().one_or_none()
    now = utc_now()
    if session is None or session["idle_expires_at"] <= now or session["absolute_expires_at"] <= now:
        raise SessionError()
    db.execute(text("""
        SELECT set_config('app.support_access_id', :support_access_id, true),
               set_config('app.clinic_id', :clinic_id, true)
    """), {"support_access_id": str(session["support_access_id"] or ""), "clinic_id": str(session["clinic_id"] or "")})
    idle_duration = timedelta(minutes=30) if session["is_platform_admin"] else timedelta(hours=8)
    db.execute(text("UPDATE sessions SET last_seen_at = :now, idle_expires_at = :idle_expires_at WHERE id = :id"), {"id": session["id"], "now": now, "idle_expires_at": min(now + idle_duration, session["absolute_expires_at"])})
    return dict(session)


def verify_csrf(session: dict, csrf_token: str) -> None:
    if hash_token(csrf_token) != session["csrf_token_hash"].strip():
        raise SessionError()


def rotate_session(db: Session, session: dict, *, mfa_verified: bool | None = None, support_access_id: UUID | None = None, clear_support_context: bool = False) -> SessionRotation:
    """Rotate the opaque session and CSRF token without extending absolute lifetime."""
    now = utc_now()
    session_token = new_opaque_token()
    csrf_token = new_csrf_token()
    absolute_expires_at = session["absolute_expires_at"]
    active_support_access_id = None if clear_support_context else (support_access_id or session.get("support_access_id"))
    idle_duration = timedelta(minutes=30) if session.get("is_platform_admin") else timedelta(hours=8)
    idle_expires_at = min(now + idle_duration, absolute_expires_at)
    db.execute(text("""
        INSERT INTO sessions
          (user_id, support_access_id, token_hash, csrf_token_hash, mfa_verified, ip_hash, user_agent, idle_expires_at, absolute_expires_at)
        VALUES (:user_id, :support_access_id, :token_hash, :csrf_hash, :mfa_verified, :ip_hash, :user_agent, :idle_expires_at, :absolute_expires_at)
    """), {"user_id": session["user_id"], "support_access_id": active_support_access_id, "token_hash": hash_token(session_token), "csrf_hash": hash_token(csrf_token), "mfa_verified": session["mfa_verified"] if mfa_verified is None else mfa_verified, "ip_hash": session.get("ip_hash") or hash_ip("unknown"), "user_agent": session.get("user_agent"), "idle_expires_at": idle_expires_at, "absolute_expires_at": absolute_expires_at})
    db.execute(text("UPDATE sessions SET revoked_at = :now WHERE id = :id AND revoked_at IS NULL"), {"now": now, "id": session["id"]})
    return SessionRotation(session_token=session_token, csrf_token=csrf_token)


def consume_manual_reset(db: Session, token: str, new_password: str) -> UUID:
    _validate_password_policy(new_password)
    now = utc_now()
    row = db.execute(
        text("SELECT id, user_id, expires_at, consumed_at FROM password_reset_tokens WHERE token_hash = :token_hash FOR UPDATE"),
        {"token_hash": hash_token(token)},
    ).mappings().one_or_none()
    if row is None or row["consumed_at"] is not None or row["expires_at"] <= now:
        raise TokenError()
    db.execute(text("UPDATE users SET password_hash = :password_hash, version = version + 1 WHERE id = :user_id"), {"password_hash": hash_password(new_password), "user_id": row["user_id"]})
    db.execute(text("UPDATE password_reset_tokens SET consumed_at = :now WHERE id = :id"), {"now": now, "id": row["id"]})
    db.execute(text("UPDATE sessions SET revoked_at = :now WHERE user_id = :user_id AND revoked_at IS NULL"), {"now": now, "user_id": row["user_id"]})
    return row["user_id"]


def create_manual_reset(db: Session, user_id: UUID) -> str:
    """Create a single-use reset secret; only its hash is persisted."""
    token = new_opaque_token()
    # Serialize issuance per user so concurrent owner actions cannot leave two
    # unconsumed reset links valid at the same time.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(CAST(:user_id AS text), 0))"), {"user_id": user_id})
    db.execute(text("DELETE FROM password_reset_tokens WHERE user_id = :user_id AND consumed_at IS NULL"), {"user_id": user_id})
    db.execute(text("""
        INSERT INTO password_reset_tokens (user_id, token_hash, expires_at)
        VALUES (:user_id, :token_hash, :expires_at)
    """), {"user_id": user_id, "token_hash": hash_token(token), "expires_at": utc_now() + timedelta(hours=1)})
    return token


def begin_mfa_enrollment(db: Session, user_id: UUID) -> tuple[str, list[str]]:
    secret = generate_totp_secret()
    codes = generate_recovery_codes()
    db.execute(text("DELETE FROM mfa_methods WHERE user_id = :user_id"), {"user_id": user_id})
    db.execute(text("INSERT INTO mfa_methods (user_id, secret_ciphertext) VALUES (:user_id, :secret)"), {"user_id": user_id, "secret": encrypt_field(secret)})
    db.execute(text("DELETE FROM recovery_codes WHERE user_id = :user_id"), {"user_id": user_id})
    db.execute(text("INSERT INTO recovery_codes (user_id, code_hash) VALUES (:user_id, :code_hash)"), [{"user_id": user_id, "code_hash": hash_recovery_code(code)} for code in codes])
    return secret, codes


def complete_mfa(db: Session, session: dict, code: str) -> SessionRotation:
    from app.core.security import decrypt_field

    secret = db.execute(text("SELECT secret_ciphertext FROM mfa_methods WHERE user_id = :user_id AND method = 'totp'"), {"user_id": session["user_id"]}).scalar_one_or_none()
    if not secret or not verify_totp(decrypt_field(secret), code):
        raise AuthenticationError()
    db.execute(text("UPDATE mfa_methods SET enrolled_at = COALESCE(enrolled_at, :now), last_used_at = :now WHERE user_id = :user_id"), {"now": utc_now(), "user_id": session["user_id"]})
    session["mfa_verified"] = True
    return rotate_session(db, session, mfa_verified=True)


def recover_mfa(db: Session, session: dict, code: str) -> SessionRotation:
    row = db.execute(text("""
        SELECT id FROM recovery_codes
        WHERE user_id = :user_id AND code_hash = :code_hash AND used_at IS NULL
        FOR UPDATE
    """), {"user_id": session["user_id"], "code_hash": hash_recovery_code(code)}).mappings().one_or_none()
    if row is None:
        raise AuthenticationError()
    db.execute(text("UPDATE recovery_codes SET used_at = :now WHERE id = :id"), {"now": utc_now(), "id": row["id"]})
    session["mfa_verified"] = True
    return rotate_session(db, session, mfa_verified=True)


def create_staff_invitation(db: Session, clinic_id: UUID, invited_by: UUID, email: str) -> str:
    token = new_opaque_token()
    db.execute(text("""
        INSERT INTO staff_invitations (clinic_id, invited_by, intended_normalized_email, token_hash, expires_at)
        VALUES (:clinic_id, :invited_by, :email, :token_hash, :expires_at)
    """), {"clinic_id": clinic_id, "invited_by": invited_by, "email": normalize_email(email), "token_hash": hash_token(token), "expires_at": utc_now() + timedelta(hours=24)})
    return token


def consume_staff_invitation(db: Session, token: str, password: str, display_name: str) -> UUID:
    _validate_password_policy(password)
    row = db.execute(text("""
        SELECT id, clinic_id, intended_normalized_email, expires_at, consumed_at, revoked_at
        FROM staff_invitations WHERE token_hash = :token_hash FOR UPDATE
    """), {"token_hash": hash_token(token)}).mappings().one_or_none()
    now = utc_now()
    if row is None or row["consumed_at"] is not None or row["revoked_at"] is not None or row["expires_at"] <= now:
        raise TokenError()
    user_id = db.execute(text("""
        INSERT INTO users (clinic_id, normalized_email, display_name, password_hash)
        VALUES (:clinic_id, :email, :display_name, :password_hash)
        RETURNING id
    """), {"clinic_id": row["clinic_id"], "email": row["intended_normalized_email"], "display_name": display_name.strip(), "password_hash": hash_password(password)}).scalar_one()
    role_id = db.execute(text("SELECT id FROM roles WHERE clinic_id IS NULL AND name = 'receptionist'" )).scalar_one()
    db.execute(text("INSERT INTO user_roles (clinic_id, user_id, role_id) VALUES (:clinic_id, :user_id, :role_id)"), {"clinic_id": row["clinic_id"], "user_id": user_id, "role_id": role_id})
    db.execute(text("UPDATE staff_invitations SET consumed_at = :now WHERE id = :id"), {"now": now, "id": row["id"]})
    return user_id
