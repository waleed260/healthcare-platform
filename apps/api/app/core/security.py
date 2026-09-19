from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone

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
