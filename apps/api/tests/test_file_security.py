import pytest

from app.core.config import get_settings
from app.core.security import generate_field_key
from app.modules.files.service import create_access_token, display_original_filename, encrypt_original_filename, generic_filename, new_storage_key, validate_magic_bytes, validate_upload, verify_access_token


def test_patient_upload_policy_rejects_unsafe_types_and_extensions() -> None:
    digest = "a" * 64
    assert validate_upload("scan.pdf", "application/pdf", 100, digest) == "scan.pdf"
    with pytest.raises(ValueError):
        validate_upload("payload.html", "text/html", 100, digest)
    with pytest.raises(ValueError):
        validate_upload("scan.png", "image/jpeg", 100, digest)
    with pytest.raises(ValueError):
        validate_upload("scan.pdf", "application/pdf", 20 * 1024 * 1024 + 1, digest)


def test_storage_keys_are_generated_and_access_tokens_are_bound() -> None:
    key = new_storage_key("clinic", "patient", "document", "display.pdf")
    assert key == "clinic/patient/document.pdf"
    token = create_access_token("document", "user", 123)
    assert verify_access_token(token, "document", "user", 123)
    assert not verify_access_token(token, "other-document", "user", 123)


def test_magic_bytes_must_match_declared_type() -> None:
    validate_magic_bytes("application/pdf", b"%PDF-1.7\n")
    validate_magic_bytes("image/jpeg", b"\xff\xd8\xff\xe0")
    validate_magic_bytes("image/png", b"\x89PNG\r\n\x1a\n")
    with pytest.raises(ValueError):
        validate_magic_bytes("application/pdf", b"not a pdf")


def test_access_tokens_are_expiry_bound() -> None:
    token = create_access_token("document", "user", 123)
    assert not verify_access_token(token, "document", "user", 124)


def test_private_document_filename_is_encrypted_and_has_a_generic_legacy_name(monkeypatch) -> None:
    monkeypatch.setenv("FIELD_ENCRYPTION_KEYS", generate_field_key())
    get_settings.cache_clear()
    try:
        ciphertext = encrypt_original_filename("synthetic-private-document.pdf")
        assert ciphertext != "synthetic-private-document.pdf"
        assert generic_filename("application/pdf") == "document.pdf"
        assert display_original_filename(ciphertext, "document.pdf", "application/pdf") == "synthetic-private-document.pdf"
        assert display_original_filename(None, "legacy-synthetic.pdf", "application/pdf") == "legacy-synthetic.pdf"
    finally:
        get_settings.cache_clear()
