from typing import Literal

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from app.modules.websites.sanitizer import validate_navigation_href
from app.modules.websites.theme import normalize_brand


class SectionContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heading: str = Field(default="", max_length=240)
    body: str = Field(default="", max_length=5000)
    eyebrow: str = Field(default="", max_length=120)
    button_label: str | None = Field(default=None, max_length=80)
    button_href: str | None = Field(default=None, max_length=500)
    items: list[dict[str, object]] = Field(default_factory=list, max_length=50)
    location: str = Field(default="", max_length=500)
    address: str = Field(default="", max_length=500)


class WebsiteSectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_type: Literal["hero", "banner", "appointment_cta", "lead_form", "doctor_profile", "services", "pricing", "faq", "testimonials", "results", "statistics", "hours", "location", "contact", "about", "legal"]
    layout_key: str = Field(min_length=1, max_length=80)
    position: int = Field(ge=0, le=100)
    content: SectionContent
    is_visible: bool = True


class WebsiteLeadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    campaign: str | None = Field(default=None, max_length=160)
    specialty_id: UUID | None = None
    requested_service_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=5000)
    consent: StrictBool


class WebsiteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    template_key: Literal["calm_clinic", "editorial_practice", "warm_studio"]
    brand: dict[str, object] = Field(default_factory=dict)

    @field_validator("brand")
    @classmethod
    def validate_brand(cls, value: dict[str, object]) -> dict[str, object]:
        return normalize_brand(value)


class WebsiteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    template_key: Literal["calm_clinic", "editorial_practice", "warm_studio"] | None = None
    brand: dict[str, object] | None = None

    @field_validator("brand")
    @classmethod
    def validate_brand(cls, value: dict[str, object] | None) -> dict[str, object] | None:
        return None if value is None else normalize_brand(value)


class WebsiteArchiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class WebsiteMediaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    alt_text: str = Field(min_length=1, max_length=240)


class WebsitePageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=160)
    seo_title: str | None = Field(default=None, max_length=160)
    seo_description: str | None = Field(default=None, max_length=320)
    canonical_url: str | None = Field(default=None, max_length=500)
    noindex: bool | None = None
    og_title: str | None = Field(default=None, max_length=160)
    og_description: str | None = Field(default=None, max_length=320)
    og_image_media_id: UUID | None = None

    @field_validator("canonical_url")
    @classmethod
    def validate_canonical(cls, value: str | None) -> str | None:
        return None if value is None or value == "" else validate_navigation_href(value)

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, value: str) -> str:
        normalized = value.strip().casefold().strip("/")
        if not normalized or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for character in normalized):
            raise ValueError("slug may contain only lowercase letters, numbers, hyphens, and underscores")
        return normalized


class WebsitePageUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    slug: str | None = Field(default=None, min_length=1, max_length=120)
    title: str | None = Field(default=None, min_length=1, max_length=160)
    seo_title: str | None = Field(default=None, max_length=160)
    seo_description: str | None = Field(default=None, max_length=320)
    canonical_url: str | None = Field(default=None, max_length=500)
    noindex: bool | None = None
    og_title: str | None = Field(default=None, max_length=160)
    og_description: str | None = Field(default=None, max_length=320)
    og_image_media_id: UUID | None = None

    @field_validator("canonical_url")
    @classmethod
    def validate_canonical(cls, value: str | None) -> str | None:
        return None if value is None or value == "" else validate_navigation_href(value)

    @field_validator("slug")
    @classmethod
    def normalize_update_slug(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return WebsitePageCreate.normalize_slug(value)


class WebsiteVersionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class WebsiteSectionEdit(WebsiteSectionUpdate):
    expected_version: int = Field(ge=1)


class WebsitePublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class WebsiteRollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_version_id: str
    expected_version: int = Field(ge=1)


class WebsiteMediaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_filename: str = Field(min_length=1, max_length=240)
    alt_text: str = Field(min_length=1, max_length=240)
    mime_type: Literal["image/jpeg", "image/png", "image/webp"]


class DomainCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hostname: str = Field(min_length=3, max_length=253)

    @field_validator("hostname")
    @classmethod
    def validate_hostname(cls, value: str) -> str:
        normalized = value.strip().rstrip(".").casefold()
        if "://" in normalized or " " in normalized or "." not in normalized or ".." in normalized:
            raise ValueError("hostname must be a normalized fully-qualified host")
        return normalized


class DomainVerify(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_proof: str = Field(min_length=20, max_length=200)


class RedirectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    from_path: str = Field(min_length=2, max_length=300, pattern=r"^/[A-Za-z0-9\-._~/]*$")
    to_path: str = Field(min_length=1, max_length=500)
    status_code: Literal[301, 302] = 301

    @field_validator("to_path")
    @classmethod
    def validate_target(cls, value: str) -> str:
        validated = validate_navigation_href(value)
        assert validated is not None
        return validated

    @field_validator("from_path")
    @classmethod
    def no_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/") or "/"
