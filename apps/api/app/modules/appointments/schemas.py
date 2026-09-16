from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID


class PublicBookingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_id: UUID
    doctor_id: UUID | None = None
    service_id: UUID
    starts_at: datetime
    full_name: str = Field(min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    date_of_birth: date | None = None
    answers: list["BookingAnswer"] = Field(default_factory=list, max_length=50)


class BookingAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: UUID
    value: str = Field(max_length=2000)


class AppointmentTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to_status: str = Field(pattern="^(confirmed|cancelled|arrived|waiting|in_consultation|completed|no_show)$")
    expected_version: int = Field(ge=1)
    reason_code: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=1000)


class AppointmentDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    reason_code: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=1000)


class AppointmentRescheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    starts_at: datetime
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)


class AppointmentAssignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doctor_id: UUID | None = None
    expected_version: int = Field(ge=1)


class PublicCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=500)


class PublicRescheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    starts_at: datetime
    reason: str = Field(min_length=1, max_length=500)
