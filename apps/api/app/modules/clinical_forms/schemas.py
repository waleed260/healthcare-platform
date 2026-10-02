import re
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

FIELD_TYPES = ("text", "textarea", "number", "select", "checkbox", "date", "media_ref")
_KEY = re.compile(r"^[a-z][a-z0-9_]{0,39}$")


class FormField(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    key: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=160)
    type: Literal["text", "textarea", "number", "select", "checkbox", "date", "media_ref"]
    required: bool = False
    options: list[str] = Field(default_factory=list, max_length=40)

    @field_validator("key")
    @classmethod
    def valid_key(cls, value: str) -> str:
        if not _KEY.fullmatch(value):
            raise ValueError("field key must start with a letter and use lowercase letters, digits or underscores")
        return value

    @field_validator("options")
    @classmethod
    def clean_options(cls, value: list[str]) -> list[str]:
        cleaned = [option.strip() for option in value if option.strip()]
        if len(cleaned) > 40 or any(len(option) > 160 for option in cleaned):
            raise ValueError("options must be 1-160 characters, at most 40")
        return cleaned


def normalize_field_schema(value: dict[str, Any]) -> dict[str, Any]:
    """Store every template as {"fields": [FormField, ...]}; tolerate a bare {} (empty form)."""
    raw = value.get("fields", []) if isinstance(value, dict) else []
    if not isinstance(raw, list):
        raise ValueError("field_schema.fields must be a list")
    if len(raw) > 60:
        raise ValueError("a form may have at most 60 fields")
    fields = [FormField.model_validate(item) for item in raw]
    keys = [field.key for field in fields]
    if len(set(keys)) != len(keys):
        raise ValueError("field keys must be unique")
    for field in fields:
        if field.type == "select" and not field.options:
            raise ValueError(f"select field '{field.key}' needs at least one option")
        if field.type != "select" and field.options:
            raise ValueError(f"only select fields take options ('{field.key}')")
    return {"fields": [field.model_dump() for field in fields]}


class FormTemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    form_key: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=160)
    specialty_id: UUID | None = None
    field_schema: dict[str, object] = Field(default_factory=dict)

    @field_validator("field_schema")
    @classmethod
    def validate_schema(cls, value: dict[str, object]) -> dict[str, object]:
        return normalize_field_schema(value)


class FormTemplateStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(pattern="^(active|archived)$")
    expected_version: int = Field(ge=1)


class FormResponseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: UUID
    appointment_id: UUID | None = None
    response_data: dict[str, object] = Field(default_factory=dict)


class FormResponseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    response_data: dict[str, object]


class FormResponseSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


def validate_answers(field_schema: dict[str, Any], data: dict[str, Any], *, require_all: bool) -> dict[str, Any]:
    """Validate a response against a template's fields. Drafts (require_all=False) may be partial."""
    fields = {f["key"]: f for f in field_schema.get("fields", [])}
    unknown = set(data) - set(fields)
    if unknown:
        raise ValueError(f"unknown fields: {', '.join(sorted(unknown))}")
    for key, field in fields.items():
        present = key in data and data[key] not in (None, "")
        if field.get("required") and require_all and not present:
            raise ValueError(f"'{field['label']}' is required")
        if not present:
            continue
        raw = data[key]
        kind = field["type"]
        if kind in ("text", "textarea", "date", "media_ref"):
            if not isinstance(raw, str) or len(raw) > 5000:
                raise ValueError(f"'{field['label']}' must be text")
            if kind == "date" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
                raise ValueError(f"'{field['label']}' must be a date (YYYY-MM-DD)")
        elif kind == "number":
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ValueError(f"'{field['label']}' must be a number")
        elif kind == "checkbox":
            if not isinstance(raw, bool):
                raise ValueError(f"'{field['label']}' must be true or false")
        elif kind == "select":
            if raw not in field["options"]:
                raise ValueError(f"'{field['label']}' must be one of the listed options")
    return data
