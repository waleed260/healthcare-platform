from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PatientMediaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    media_kind: str = Field(default="other", pattern="^(before|after|other)$")
    captured_on: date | None = None
    treatment_plan_item_id: UUID | None = None
    provider_user_id: UUID | None = None


class PatientMediaApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    consent_record_id: UUID


class PatientMediaRevoke(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
