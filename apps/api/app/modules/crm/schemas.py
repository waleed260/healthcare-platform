from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PatientCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    date_of_birth: date | None = None


class PatientUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)


class ContactCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_type: str = Field(min_length=1, max_length=40)
    value: str = Field(min_length=1, max_length=320)
    is_primary: bool = False


class TagCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)


class PatientMerge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_patient_id: UUID
    reason: str = Field(min_length=1, max_length=500)


class PatientNoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=10000)
    note_type: str = Field(default="general", min_length=1, max_length=40)
    visibility: str = Field(default="clinic", pattern="^(clinic|private_doctor)$")


class PatientNoteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    body: str | None = Field(default=None, min_length=1, max_length=10000)
    note_type: str | None = Field(default=None, min_length=1, max_length=40)
    visibility: str | None = Field(default=None, pattern="^(clinic|private_doctor)$")

    @model_validator(mode="after")
    def requires_a_change(self):
        if self.body is None and self.note_type is None and self.visibility is None:
            raise ValueError("at least one note field must be provided")
        return self


class ConsentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    consent_type: str = Field(min_length=1, max_length=80)
    status: str = Field(pattern="^(granted|withdrawn|declined)$")
    version: str = Field(min_length=1, max_length=40)


class ConsentRevoke(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
