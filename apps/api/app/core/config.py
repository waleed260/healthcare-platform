import os
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
    database_connect_timeout: int = Field(default=2, ge=1, le=60)
    session_hmac_key: str = "local-development-session-hmac-key-change-me"
    field_encryption_key: str = Field(default="", validation_alias=AliasChoices("FIELD_ENCRYPTION_KEYS", "FIELD_ENCRYPTION_KEY"))
    cookie_domain: str = ""
    # Which peers uvicorn may trust X-Forwarded-For/Proto from (comma-separated
    # IPs or CIDRs, or "*"). A wildcard lets any direct client spoof the client
    # IP that feeds per-IP login rate limiting and audit attribution, so it must
    # be an explicit, deliberate choice — see validate_forwarded_ip_trust.
    forwarded_allow_ips: str = "127.0.0.1"
    allow_wildcard_forwarded_ips: bool = False
    csrf_allowed_origins: str = "http://localhost:3000"
    cors_origins: str = ""
    sentry_dsn: str = ""
    vapid_subject: str = ""
    vapid_private_key: str = ""
    vapid_public_key: str = ""
    session_cookie_name: str = "healthcare_session"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""
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
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def google_callback_url(self) -> str:
        return self.google_redirect_uri or f"{self.public_app_url.rstrip('/')}/api/v1/auth/google/callback"

    @property
    def push_enabled(self) -> bool:
        """Browser push delivery is optional; it requires a VAPID identity."""
        return bool(self.vapid_subject and self.vapid_private_key)

    @property
    def field_encryption_keys(self) -> tuple[str, ...]:
        """Return the active encryption key followed by optional retired keys.

        ``FIELD_ENCRYPTION_KEYS`` is comma-separated so decryption can survive
        a staged key rotation. New ciphertext is always written with item zero.
        """
        return tuple(key.strip() for key in self.field_encryption_key.split(",") if key.strip())

    @model_validator(mode="after")
    def validate_push_configuration(self) -> "Settings":
        # Push delivery stays opt-in, but a partially configured VAPID identity
        # must fail closed rather than silently dropping browser notifications.
        if self.vapid_subject or self.vapid_private_key or self.vapid_public_key:
            if not (self.vapid_subject and self.vapid_private_key):
                raise ValueError("VAPID_SUBJECT and VAPID_PRIVATE_KEY must be configured together")
            if not (self.vapid_subject.startswith("mailto:") or self.vapid_subject.startswith("https://")):
                raise ValueError("VAPID_SUBJECT must be a mailto: or https URL")
        return self

    @model_validator(mode="after")
    def reject_tenant_fault_injection_outside_tests(self) -> "Settings":
        if self.app_env != "test" and os.environ.get("BREAK_TENANT_ISOLATION") == "1":
            raise ValueError("BREAK_TENANT_ISOLATION is test-only and cannot be enabled outside APP_ENV=test")
        return self

    @model_validator(mode="after")
    def validate_forwarded_ip_trust(self) -> "Settings":
        # Fail closed on a wildcard forwarded-IP trust in production: it would let
        # a client that can reach the API directly spoof X-Forwarded-For and defeat
        # per-IP rate limiting. Operators who really front the API with a trusted
        # proxy on an unknown source range must opt in explicitly.
        if self.app_env == "production" and "*" in self.forwarded_allow_ips and not self.allow_wildcard_forwarded_ips:
            raise ValueError("FORWARDED_ALLOW_IPS must name trusted proxy IPs/CIDRs in production; set ALLOW_WILDCARD_FORWARDED_IPS=true only if you deliberately trust every peer")
        return self

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
