from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AvailabilityRuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_id: UUID
    doctor_id: UUID
    service_id: UUID | None = None
    weekday: int = Field(ge=0, le=6)
    starts_at: time
    ends_at: time
    effective_from: date
    effective_to: date | None = None
    slot_cadence_minutes: int = Field(default=15, ge=1, le=240)

    @model_validator(mode="after")
    def ordered(self):
        if self.starts_at >= self.ends_at or (self.effective_to is not None and self.effective_to < self.effective_from):
            raise ValueError("availability interval and effective dates must be ordered")
        return self


class TimeBlockCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    starts_at: datetime
    ends_at: datetime
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def ordered(self):
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None or self.starts_at >= self.ends_at:
            raise ValueError("time blocks require timezone-aware ordered timestamps")
        return self


class LeaveBlockCreate(TimeBlockCreate):
    doctor_id: UUID
    branch_id: UUID | None = None


class BlockedSlotCreate(TimeBlockCreate):
    branch_id: UUID
    doctor_id: UUID | None = None


class ResourceBlockCreate(TimeBlockCreate):
    resource_id: UUID
