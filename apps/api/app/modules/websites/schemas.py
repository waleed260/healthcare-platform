from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SectionContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heading: str = Field(default="", max_length=240)
    body: str = Field(default="", max_length=5000)
    button_label: str | None = Field(default=None, max_length=80)
    button_href: str | None = Field(default=None, max_length=500)


class WebsiteSectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_type: Literal["hero", "appointment_cta", "doctor_profile", "services", "faq", "hours", "location", "about", "legal"]
    layout_key: str = Field(min_length=1, max_length=80)
    position: int = Field(ge=0, le=100)
    content: SectionContent
    is_visible: bool = True


class WebsiteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    template_key: Literal["calm_clinic", "editorial_practice", "warm_studio"]
    brand: dict[str, object] = Field(default_factory=dict)


class WebsiteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    template_key: Literal["calm_clinic", "editorial_practice", "warm_studio"] | None = None
    brand: dict[str, object] | None = None


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
