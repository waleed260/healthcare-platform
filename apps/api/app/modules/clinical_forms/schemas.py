from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FormTemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    form_key: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=160)
    specialty_id: UUID | None = None
    field_schema: dict[str, object] = Field(default_factory=dict)


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
