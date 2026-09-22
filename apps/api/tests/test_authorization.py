from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.authorization.permissions import PERMISSIONS, validate_permission_code
from app.modules.authorization.service import require_permission


def test_permission_catalog_rejects_unknown_codes() -> None:
    assert validate_permission_code("clinic.read") == "clinic.read"
    assert {"patient.private_note.read", "appointment.reschedule", "admin.support.access", "staff.password_reset"}.issubset(PERMISSIONS)
    with pytest.raises(ValueError):
        validate_permission_code("patients.read.all")


def test_require_permission_rejects_unknown_codes_before_database_access() -> None:
    with pytest.raises(ValueError, match="unknown permission code"):
        require_permission(None, uuid4(), uuid4(), "patients.read.all")  # type: ignore[arg-type]


def test_production_configuration_fails_closed_without_secrets() -> None:
    with pytest.raises(ValueError, match="SESSION_HMAC_KEY"):
        Settings(app_env="production")


def test_production_configuration_requires_sentry_monitoring() -> None:
    with pytest.raises(ValueError, match="SENTRY_DSN"):
        Settings(
            app_env="production",
            session_hmac_key="synthetic-session-key",
            field_encryption_key="synthetic-encryption-key",
            database_url="postgresql+psycopg://runtime:secret@db.internal/healthcare",
            database_migration_url="postgresql+psycopg://migrator:secret@db.internal/healthcare",
            cookie_domain=".example.test",
            csrf_allowed_origins="https://app.example.test",
            cors_origins="https://app.example.test",
            public_app_url="https://app.example.test",
            storage_backend="supabase",
            supabase_url="https://storage.example.test",
            supabase_service_role_key="synthetic-service-key",
        )


def test_valid_production_configuration_is_accepted() -> None:
    settings = Settings(
        app_env="production",
        session_hmac_key="synthetic-session-key",
        field_encryption_key="synthetic-encryption-key",
        database_url="postgresql+psycopg://runtime:secret@db.internal/healthcare",
        database_migration_url="postgresql+psycopg://migrator:secret@db.internal/healthcare",
        cookie_domain=".example.test",
        csrf_allowed_origins="https://app.example.test",
        cors_origins="https://app.example.test",
        public_app_url="https://app.example.test",
        public_website_domain="example.test",
        storage_backend="supabase",
        supabase_url="https://storage.example.test",
        supabase_service_role_key="synthetic-service-key",
        sentry_dsn="https://synthetic@sentry.example.test/1",
    )

    assert settings.app_env == "production"
    assert settings.cors_allowed_origins == {"https://app.example.test"}


def test_configuration_uses_only_deployed_environment_contract() -> None:
    with pytest.raises(ValueError):
        Settings(app_env="development")


def test_storage_backend_is_allowlisted() -> None:
    with pytest.raises(ValueError, match="STORAGE_BACKEND"):
        Settings(storage_backend="filesystem")


def test_uuid_generation_is_available_for_scope_fixtures() -> None:
    assert uuid4() != uuid4()
