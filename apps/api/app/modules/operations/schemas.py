from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class QueueCheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    appointment_id: UUID
    expected_version: int = Field(ge=1)


class QueueCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class QueueReorder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    priority: int = Field(ge=0, le=100)
    priority_reason: str | None = Field(default=None, max_length=240)


class FollowUpCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: UUID
    appointment_id: UUID | None = None
    assignee_user_id: UUID | None = None
    reason: str = Field(min_length=1, max_length=500)
    due_at: datetime
    priority: str = Field(default="normal", pattern="^(low|normal|high)$")


class FollowUpComplete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    outcome_note: str | None = Field(default=None, max_length=2000)


class FollowUpUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, min_length=1, max_length=500)
    due_at: datetime | None = None
    priority: str | None = Field(default=None, pattern="^(low|normal|high)$")

    @model_validator(mode="after")
    def requires_a_change(self):
        if self.reason is None and self.due_at is None and self.priority is None:
            raise ValueError("at least one follow-up field must be provided")
        return self


class FollowUpAssign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    assignee_user_id: UUID | None = None


class NotificationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notification_ids: list[UUID] = Field(min_length=1, max_length=100)


class PushSubscriptionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: HttpUrl
    p256dh: str = Field(min_length=1, max_length=500)
    auth: str = Field(min_length=1, max_length=500)

    @field_validator("endpoint")
    @classmethod
    def require_https(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https":
            raise ValueError("push endpoint must use HTTPS")
        return value
