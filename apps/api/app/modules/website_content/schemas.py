import re
from datetime import date
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FieldType = Literal["text", "textarea", "phone", "email", "dropdown", "checkbox", "date", "consent"]
MAPS_TO = ("full_name", "email", "phone", "notes")
KEY = re.compile(r"^[a-z][a-z0-9_]{0,39}$")


class FormField(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    key: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=120)
    type: FieldType
    required: bool = False
    options: list[str] = Field(default_factory=list, max_length=30)
    maps_to: Literal["full_name", "email", "phone", "notes"] | None = None

    @field_validator("key")
    @classmethod
    def valid_key(cls, value: str) -> str:
        if not KEY.fullmatch(value):
            raise ValueError("field keys must be lowercase letters, digits or underscores and start with a letter")
        return value

    @model_validator(mode="after")
    def check_options(self) -> "FormField":
        if self.type == "dropdown" and not self.options:
            raise ValueError("dropdown fields need at least one option")
        if self.type != "dropdown" and self.options:
            raise ValueError("only dropdown fields take options")
        if any(not option.strip() or len(option) > 120 for option in self.options):
            raise ValueError("options must be 1-120 characters")
        return self


def _validate_fields(fields: list[FormField]) -> list[FormField]:
    keys = [field.key for field in fields]
    if len(set(keys)) != len(keys):
        raise ValueError("field keys must be unique")
    mapped = [field.maps_to for field in fields if field.maps_to]
    if len(set(mapped)) != len(mapped):
        raise ValueError("each lead property can be mapped by only one field")
    if "full_name" not in mapped:
        raise ValueError("a field must be mapped to full_name")
    if "email" not in mapped and "phone" not in mapped:
        raise ValueError("a form needs an email or phone field so staff can respond")
    if not any(field.type == "consent" and field.required for field in fields):
        raise ValueError("a required consent field is mandatory")
    return fields


class FormCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    fields: list[FormField] = Field(min_length=1, max_length=25)
    action: Literal["lead", "appointment_request"] = "lead"
    specialty_id: UUID | None = None
    branch_id: UUID | None = None
    notify_user_ids: list[UUID] = Field(default_factory=list, max_length=20)
    success_message: str = Field(default="Thanks, we will be in touch shortly.", min_length=1, max_length=300)

    _fields = field_validator("fields")(lambda cls, v: _validate_fields(v))


class FormUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    fields: list[FormField] | None = Field(default=None, min_length=1, max_length=25)
    action: Literal["lead", "appointment_request"] | None = None
    specialty_id: UUID | None = None
    branch_id: UUID | None = None
    notify_user_ids: list[UUID] | None = Field(default=None, max_length=20)
    success_message: str | None = Field(default=None, min_length=1, max_length=300)
    status: Literal["active", "archived"] | None = None

    @field_validator("fields")
    @classmethod
    def check_fields(cls, value: list[FormField] | None) -> list[FormField] | None:
        return None if value is None else _validate_fields(value)


class FormSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: dict[str, Any] = Field(max_length=40)


def validate_answers(fields: list[dict[str, Any]], answers: dict[str, Any]) -> dict[str, str]:
    """Validate public answers against a stored form definition; returns cleaned string values."""
    known = {field["key"] for field in fields}
    unknown = set(answers) - known
    if unknown:
        raise ValueError(f"unknown fields: {', '.join(sorted(unknown))}")
    cleaned: dict[str, str] = {}
    for field in fields:
        raw = answers.get(field["key"])
        kind = field["type"]
        if kind in ("checkbox", "consent"):
            if raw is not None and not isinstance(raw, bool):
                raise ValueError(f"{field['label']} must be true or false")
            if field["required"] and raw is not True:
                raise ValueError(f"{field['label']} is required")
            cleaned[field["key"]] = "yes" if raw is True else "no"
            continue
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            if field["required"]:
                raise ValueError(f"{field['label']} is required")
            continue
        if not isinstance(raw, str):
            raise ValueError(f"{field['label']} must be text")
        value = raw.strip()
        limit = 2000 if kind == "textarea" else 320 if kind == "email" else 200
        if len(value) > limit:
            raise ValueError(f"{field['label']} is too long")
        if kind == "email" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError(f"{field['label']} must be a valid email")
        if kind == "phone" and not re.fullmatch(r"\+?[0-9 ()\-]{6,30}", value):
            raise ValueError(f"{field['label']} must be a valid phone number")
        if kind == "date":
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(f"{field['label']} must be a date (YYYY-MM-DD)") from exc
        if kind == "dropdown" and value not in field["options"]:
            raise ValueError(f"{field['label']} must be one of the listed options")
        cleaned[field["key"]] = value
    return cleaned


class PostCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    slug: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    title: str = Field(min_length=1, max_length=200)
    excerpt: str = Field(default="", max_length=400)
    body: str = Field(default="", max_length=50000)
    seo_title: str | None = Field(default=None, max_length=160)
    seo_description: str | None = Field(default=None, max_length=320)


class PostUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_version: int = Field(ge=1)
    slug: str | None = Field(default=None, min_length=1, max_length=120, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    excerpt: str | None = Field(default=None, max_length=400)
    body: str | None = Field(default=None, max_length=50000)
    seo_title: str | None = Field(default=None, max_length=160)
    seo_description: str | None = Field(default=None, max_length=320)


class PostStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    status: Literal["draft", "published", "archived"]


class TestimonialCreate(BaseModel):
    __test__ = False
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    author_name: str = Field(min_length=1, max_length=120)
    rating: int = Field(ge=1, le=5)
    body: str = Field(min_length=1, max_length=1500)
    consent_confirmed: bool


class TestimonialModerate(BaseModel):
    __test__ = False
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    status: Literal["pending", "approved", "rejected"]
