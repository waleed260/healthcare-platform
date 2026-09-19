from __future__ import annotations

import hashlib
import hmac
import re
from pathlib import PurePosixPath

from app.core.security import decrypt_field, encrypt_field, hash_token, new_opaque_token

MAX_PATIENT_DOCUMENT_BYTES = 20 * 1024 * 1024
ALLOWED_TYPES = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}
MAGIC_PREFIXES = {
    "application/pdf": (b"%PDF-",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
}


class MetadataEncryptionError(RuntimeError):
    """Raised without exposing a key, ciphertext, or patient metadata."""


def generic_filename(mime_type: str) -> str:
    """A backwards-compatible non-sensitive filename for legacy readers."""
    extension = ALLOWED_TYPES.get(mime_type)
    if extension is None:
        raise ValueError("file type is not permitted")
    return f"document{extension}"


def encrypt_original_filename(filename: str) -> str:
    try:
        return encrypt_field(filename)
    except (RuntimeError, ValueError) as exc:
        raise MetadataEncryptionError("private metadata encryption is unavailable") from exc


def display_original_filename(ciphertext: str | None, legacy_filename: str | None, mime_type: str) -> str:
    """Decrypt the authorized display name, falling back only for legacy rows."""
    try:
        value = decrypt_field(ciphertext) if ciphertext else legacy_filename
    except (RuntimeError, ValueError) as exc:
        raise MetadataEncryptionError("private metadata decryption is unavailable") from exc
    if not value:
        return generic_filename(mime_type)
    safe_name = PurePosixPath(value.replace("\\", "/")).name
    if not safe_name or "\x00" in safe_name:
        raise MetadataEncryptionError("private metadata is invalid")
    return safe_name


def validate_upload(filename: str, mime_type: str, size_bytes: int, content_sha256: str) -> str:
    """Validate metadata before an object is accepted into pending_scan."""
    safe_name = PurePosixPath(filename.replace("\\", "/")).name
    if not safe_name or "\x00" in safe_name:
        raise ValueError("invalid filename")
    if mime_type not in ALLOWED_TYPES:
        raise ValueError("file type is not permitted")
    if not size_bytes or size_bytes > MAX_PATIENT_DOCUMENT_BYTES:
        raise ValueError("file is too large")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", content_sha256):
        raise ValueError("content_sha256 must be a SHA-256 digest")
    if not safe_name.casefold().endswith(ALLOWED_TYPES[mime_type]):
        raise ValueError("filename extension does not match MIME type")
    return safe_name


def validate_magic_bytes(mime_type: str, content_prefix: bytes) -> None:
    """Verify that object bytes match the declared allowlisted media type."""
    expected = MAGIC_PREFIXES.get(mime_type)
    if expected is None or not any(content_prefix.startswith(prefix) for prefix in expected):
        raise ValueError("file contents do not match the declared MIME type")


def new_storage_key(clinic_id: str, patient_id: str, document_id: str, filename: str) -> str:
    """Generate a non-user-controlled private bucket key."""
    extension = PurePosixPath(filename).suffix.casefold()
    return f"{clinic_id}/{patient_id}/{document_id}{extension}"


def create_access_token(document_id: str, user_id: str, expires_at: int) -> str:
    nonce = new_opaque_token()
    signature = hash_token(f"document:{document_id}:{user_id}:{expires_at}:{nonce}")
    return f"{nonce}.{signature}"


def verify_access_token(token: str, document_id: str, user_id: str, expires_at: int) -> bool:
    try:
        nonce, signature = token.split(".", 1)
    except ValueError:
        return False
    expected = hash_token(f"document:{document_id}:{user_id}:{expires_at}:{nonce}")
    return hmac.compare_digest(signature, expected)
