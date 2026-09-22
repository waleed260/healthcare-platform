from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Healthcare Platform API"
    app_env: Literal["local", "test", "staging", "production"] = "local"
    api_version: str = "v1"
    database_url: str = "postgresql+psycopg://healthcare_runtime:healthcare_runtime_dev@localhost:5432/healthcare"
    database_migration_url: str = ""
    session_hmac_key: str = "local-development-session-hmac-key-change-me"
    field_encryption_key: str = Field(default="", validation_alias=AliasChoices("FIELD_ENCRYPTION_KEYS", "FIELD_ENCRYPTION_KEY"))
    cookie_domain: str = ""
    csrf_allowed_origins: str = "http://localhost:3000"
    cors_origins: str = ""
    sentry_dsn: str = ""
    session_cookie_name: str = "healthcare_session"
    public_app_url: str = "http://localhost:3000"
    public_website_domain: str = ""
    private_storage_root: str = "/tmp/healthcare-private"
    public_storage_root: str = "/tmp/healthcare-public"
    storage_backend: str = "local"
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_private_bucket: str = "private-healthcare"
    supabase_public_bucket: str = "public-healthcare"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    @property
    def allowed_origins(self) -> set[str]:
        return {origin.strip() for origin in self.csrf_allowed_origins.split(",") if origin.strip()}

    @property
    def cors_allowed_origins(self) -> set[str]:
        value = self.cors_origins or self.csrf_allowed_origins
        return {origin.strip() for origin in value.split(",") if origin.strip()}

    @property
    def field_encryption_keys(self) -> tuple[str, ...]:
        """Return the active encryption key followed by optional retired keys.

        ``FIELD_ENCRYPTION_KEYS`` is comma-separated so decryption can survive
        a staged key rotation. New ciphertext is always written with item zero.
        """
        return tuple(key.strip() for key in self.field_encryption_key.split(",") if key.strip())

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.storage_backend not in {"local", "supabase"}:
            raise ValueError("STORAGE_BACKEND must be local or supabase")
        if self.app_env == "production":
            missing = []
            if self.session_hmac_key == "local-development-session-hmac-key-change-me":
                missing.append("SESSION_HMAC_KEY")
            if not self.field_encryption_keys:
                missing.append("FIELD_ENCRYPTION_KEYS")
            if self.database_url.startswith("postgresql+psycopg://healthcare_runtime:healthcare_runtime_dev@localhost"):
                missing.append("DATABASE_URL")
            if not self.database_migration_url:
                missing.append("DATABASE_MIGRATION_URL")
            if not self.cookie_domain:
                missing.append("COOKIE_DOMAIN")
            if any(not origin.startswith("https://") for origin in self.allowed_origins):
                missing.append("CSRF_ALLOWED_ORIGINS(HTTPS)")
            if any(not origin.startswith("https://") for origin in self.cors_allowed_origins):
                missing.append("CORS_ORIGINS(HTTPS)")
            if not self.public_app_url.startswith("https://"):
                missing.append("PUBLIC_APP_URL(HTTPS)")
            if not self.sentry_dsn:
                missing.append("SENTRY_DSN")
            if self.storage_backend != "supabase":
                missing.append("STORAGE_BACKEND(supabase)")
            elif not self.supabase_url.startswith("https://") or not self.supabase_service_role_key:
                missing.append("SUPABASE_URL/SERVICE_ROLE_KEY")
            if missing:
                raise ValueError(f"Production configuration is missing: {', '.join(missing)}")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
