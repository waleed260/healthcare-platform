from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from uuid import UUID

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def new_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    key = get_settings().session_hmac_key.encode()
    return hmac.new(key, token.encode(), hashlib.sha256).hexdigest()


def encode_cursor(namespace: str, values: dict[str, str]) -> str:
    """Create a tamper-evident, URL-safe cursor for a stable collection order."""
    payload = json.dumps({"namespace": namespace, "values": values}, sort_keys=True, separators=(",", ":"))
    encoded = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    return f"{encoded}.{hash_token(f'cursor:{encoded}')}"


def decode_cursor(cursor: str, namespace: str) -> dict[str, str] | None:
    """Decode a cursor only when its signature and collection namespace match."""
    try:
        encoded, signature = cursor.split(".", 1)
        if not hmac.compare_digest(signature, hash_token(f"cursor:{encoded}")):
            return None
        decoded = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        payload = json.loads(decoded)
        values = payload["values"]
        if payload["namespace"] != namespace or not isinstance(values, dict):
            return None
        if not all(isinstance(key, str) and isinstance(value, str) for key, value in values.items()):
            return None
        return values
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def cursor_payload(
    cursor: str | None,
    namespace: str,
    *,
    uuid_keys: tuple[str, ...] = (),
    datetime_keys: tuple[str, ...] = (),
) -> dict[str, str] | None:
    """Decode a signed cursor and format-validate its typed components.

    Returns the values dict (all strings) when the cursor is valid, or ``None``
    when it is absent, tampered, from another collection, or carries a value
    that is not a well-formed UUID / ISO-8601 timestamp. List endpoints map a
    ``None`` for a non-empty cursor to a 400, so a malformed-but-validly-signed
    cursor can never reach the query and raise a 500 at ``CAST`` time. Keeping
    the parse here lets every keyset query bind its cursor as strings wrapped in
    explicit ``CAST(... AS uuid/timestamptz)``, which is safe under server-side
    binding instead of relying on ClientCursor literal coercion.
    """
    if not cursor:
        return None
    values = decode_cursor(cursor, namespace)
    if values is None:
        return None
    try:
        for key in uuid_keys:
            if values.get(key) is not None:
                UUID(values[key])
        for key in datetime_keys:
            if values.get(key) is not None:
                datetime.fromisoformat(values[key])
    except (ValueError, TypeError):
        return None
    return values


def hash_ip(ip_address: str) -> str:
    return hash_token(f"ip:{ip_address}")


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def encrypt_field(value: str) -> str:
    keys = get_settings().field_encryption_keys
    if not keys:
        raise RuntimeError("FIELD_ENCRYPTION_KEYS is required for encrypted fields")
    return Fernet(keys[0].encode()).encrypt(value.encode()).decode()


def decrypt_field(value: str) -> str:
    keys = get_settings().field_encryption_keys
    if not keys:
        raise RuntimeError("FIELD_ENCRYPTION_KEYS is required for encrypted fields")
    for key in keys:
        try:
            return Fernet(key.encode()).decrypt(value.encode()).decode()
        except InvalidToken:
            continue
    raise ValueError("encrypted field could not be decrypted with configured keys")


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def generate_recovery_codes(count: int = 10) -> list[str]:
    return [secrets.token_urlsafe(9) for _ in range(count)]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hash_recovery_code(code: str) -> str:
    return hash_token(f"recovery:{code}")


def generate_field_key() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
