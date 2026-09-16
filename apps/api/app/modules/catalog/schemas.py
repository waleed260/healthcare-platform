from datetime import date, time
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ServiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    category: str | None = Field(default=None, max_length=120)
    short_description: str | None = Field(default=None, max_length=500)
    full_description: str | None = Field(default=None, max_length=5000)
    duration_minutes: int = Field(gt=0, le=1440)
    buffer_before_minutes: int = Field(default=0, ge=0, le=240)
    buffer_after_minutes: int = Field(default=0, ge=0, le=240)
    price_mode: Literal["exact", "range", "starting_at", "contact"] = "contact"
    amount_minor: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    approval_mode: Literal["instant", "staff_approval"] = "staff_approval"
    visibility: Literal["public", "hidden"] = "public"


class ServiceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    category: str | None = Field(default=None, max_length=120)
    short_description: str | None = Field(default=None, max_length=500)
    full_description: str | None = Field(default=None, max_length=5000)
    duration_minutes: int | None = Field(default=None, gt=0, le=1440)
    buffer_before_minutes: int | None = Field(default=None, ge=0, le=240)
    buffer_after_minutes: int | None = Field(default=None, ge=0, le=240)
    price_mode: Literal["exact", "range", "starting_at", "contact"] | None = None
    amount_minor: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    approval_mode: Literal["instant", "staff_approval"] | None = None
    visibility: Literal["public", "hidden"] | None = None

    @model_validator(mode="after")
    def require_change(self):
        if not any(getattr(self, field) is not None for field in type(self).model_fields if field != "expected_version"):
            raise ValueError("at least one service field must be supplied")
        return self


class BranchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=160)
    timezone: str = Field(min_length=1, max_length=80)
    address: dict[str, str] = Field(default_factory=dict)
    phone: str | None = Field(default=None, max_length=40)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return value


class BranchUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    code: str | None = Field(default=None, min_length=1, max_length=40)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    timezone: str | None = Field(default=None, min_length=1, max_length=80)
    address: dict[str, str] | None = None
    phone: str | None = Field(default=None, max_length=40)

    @field_validator("timezone")
    @classmethod
    def validate_update_timezone(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ZoneInfo(value)
            except ZoneInfoNotFoundError as exc:
                raise ValueError("timezone must be a valid IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def require_change(self):
        if not any(getattr(self, field) is not None for field in ("code", "name", "timezone", "address", "phone")):
            raise ValueError("at least one branch field must be supplied")
        return self

class BranchHoursUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weekday: int = Field(ge=0, le=6)
    interval_index: int = Field(default=0, ge=0, le=20)
    opens_at: time | None = None
    closes_at: time | None = None
    is_closed: bool = False


class DoctorCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_name: str = Field(min_length=1, max_length=160)
    specialty: str | None = Field(default=None, max_length=160)
    registration: str | None = Field(default=None, max_length=120)
    bio: str | None = Field(default=None, max_length=5000)
    consultation_duration_minutes: int = Field(gt=0, le=1440)


class DoctorUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    public_name: str | None = Field(default=None, min_length=1, max_length=160)
    specialty: str | None = Field(default=None, max_length=160)
    registration: str | None = Field(default=None, max_length=120)
    bio: str | None = Field(default=None, max_length=5000)
    consultation_duration_minutes: int | None = Field(default=None, gt=0, le=1440)

    @model_validator(mode="after")
    def require_change(self):
        if not any(getattr(self, field) is not None for field in ("public_name", "specialty", "registration", "bio", "consultation_duration_minutes")):
            raise ValueError("at least one doctor field must be supplied")
        return self


class HolidayCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    holiday_date: date
    name: str = Field(min_length=1, max_length=160)
    branch_id: UUID | None = None
    starts_at: time | None = None
    ends_at: time | None = None

    @model_validator(mode="after")
    def validate_interval(self):
        if (self.starts_at is None) != (self.ends_at is None):
            raise ValueError("holiday start and end times must be supplied together")
        if self.starts_at is not None and self.starts_at >= self.ends_at:
            raise ValueError("holiday end time must be after start time")
        return self


class RoomCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)


class RoomUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=120)

    @model_validator(mode="after")
    def require_change(self):
        if self.name is None:
            raise ValueError("room name must be supplied")
        return self


class ResourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    capacity: int = Field(default=1, ge=1, le=1)


class ResourceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    capacity: int | None = Field(default=None, ge=1, le=1)

    @model_validator(mode="after")
    def require_change(self):
        if self.name is None and self.capacity is None:
            raise ValueError("at least one resource field must be supplied")
        return self


class CatalogStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(pattern="^(active|archived)$")
