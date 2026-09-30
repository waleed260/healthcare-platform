from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TreatmentPlanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: UUID
    title: str = Field(min_length=1, max_length=200)
    diagnosis: str | None = Field(default=None, max_length=500)
    starts_on: date | None = None
    ends_on: date | None = None


class TreatmentPlanUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    diagnosis: str | None = Field(default=None, max_length=500)
    status: str | None = Field(default=None, pattern="^(draft|active|completed|cancelled)$")
    starts_on: date | None = None
    ends_on: date | None = None


class TreatmentPlanItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    service_id: UUID | None = None
    appointment_id: UUID | None = None
    assigned_doctor_id: UUID | None = None
    instructions: str | None = Field(default=None, max_length=2000)
    due_on: date | None = None
    sort_order: int = Field(default=0, ge=0, le=10000)


class TreatmentPlanItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    instructions: str | None = Field(default=None, max_length=2000)
    status: str | None = Field(default=None, pattern="^(planned|in_progress|completed|skipped)$")
    due_on: date | None = None
    sort_order: int | None = Field(default=None, ge=0, le=10000)


class PrescriptionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    medication_name: str = Field(min_length=1, max_length=200)
    appointment_id: UUID | None = None
    dosage: str | None = Field(default=None, max_length=200)
    frequency: str | None = Field(default=None, max_length=200)
    duration: str | None = Field(default=None, max_length=200)
    instructions: str | None = Field(default=None, max_length=2000)


class PrescriptionStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    status: str = Field(pattern="^(active|completed|discontinued)$")
