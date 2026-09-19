from app.core.security import (
    decrypt_field,
    decode_cursor,
    encrypt_field,
    generate_field_key,
    encode_cursor,
    generate_recovery_codes,
    generate_totp_secret,
    hash_password,
    hash_token,
    verify_password,
    verify_totp,
)
from app.core.config import get_settings


def test_argon2id_password_hashes_are_not_reversible() -> None:
    password_hash = hash_password("A-strong-test-password-123")
    assert password_hash.startswith("$argon2id$")
    assert verify_password(password_hash, "A-strong-test-password-123")
    assert not verify_password(password_hash, "wrong-password-123" )


def test_opaque_token_hash_is_deterministic_but_not_plaintext() -> None:
    token = "synthetic-session-token"
    assert hash_token(token) == hash_token(token)
    assert hash_token(token) != token


def test_totp_and_recovery_code_generation() -> None:
    secret = generate_totp_secret()
    import pyotp

    assert verify_totp(secret, pyotp.TOTP(secret).now())
    assert len(generate_recovery_codes()) == 10


def test_collection_cursor_is_signed_and_namespace_bound() -> None:
    cursor = encode_cursor("patients", {"full_name": "Synthetic Patient", "id": "00000000-0000-0000-0000-000000000001"})
    assert decode_cursor(cursor, "patients") == {"full_name": "Synthetic Patient", "id": "00000000-0000-0000-0000-000000000001"}
    assert decode_cursor(cursor + "x", "patients") is None
    assert decode_cursor(cursor, "appointments") is None


def test_field_encryption_supports_staged_key_rotation(monkeypatch) -> None:
    old_key, new_key = generate_field_key(), generate_field_key()
    monkeypatch.setenv("FIELD_ENCRYPTION_KEYS", old_key)
    get_settings.cache_clear()
    old_ciphertext = encrypt_field("synthetic private value")

    monkeypatch.setenv("FIELD_ENCRYPTION_KEYS", f"{new_key},{old_key}")
    get_settings.cache_clear()
    assert decrypt_field(old_ciphertext) == "synthetic private value"
    assert decrypt_field(encrypt_field("new synthetic private value")) == "new synthetic private value"
    get_settings.cache_clear()
