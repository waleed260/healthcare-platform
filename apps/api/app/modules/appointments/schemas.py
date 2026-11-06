import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from uuid import UUID

# Permissive international phone pattern: allow + and digits/spaces/dashes/parens,
# require at least 7 digits total — matches the frontend hint.
_PHONE_DIGITS = re.compile(r"\d")


def _validate_phone(value: str) -> str:
    cleaned = value.strip()
    digits = _PHONE_DIGITS.findall(cleaned)
    if len(digits) < 7:
        raise ValueError("phone number must contain at least 7 digits")
    return cleaned


class PublicBookingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_id: UUID
    doctor_id: UUID | None = None
    service_id: UUID
    starts_at: datetime
    full_name: str = Field(min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=320)
    phone: str = Field(min_length=1, max_length=40)
    date_of_birth: date | None = None
    answers: list["BookingAnswer"] = Field(default_factory=list, max_length=50)

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, value: str) -> str:
        return _validate_phone(value)


class InternalBookingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_id: UUID
    doctor_id: UUID | None = None
    service_id: UUID
    starts_at: datetime
    patient_id: UUID | None = None
    full_name: str | None = Field(default=None, max_length=160)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    date_of_birth: date | None = None
    appointment_type: str | None = Field(default=None, max_length=20)
    payment_method: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def _require_phone_for_new_patient(self) -> "InternalBookingRequest":
        if self.patient_id is None:
            if not self.phone or not self.phone.strip():
                raise ValueError("phone is required when creating a new patient")
            _validate_phone(self.phone)
        elif self.phone:
            _validate_phone(self.phone)
        return self


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
