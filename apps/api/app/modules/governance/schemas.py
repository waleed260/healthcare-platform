from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.authorization.permissions import validate_permission_code


class SubscriptionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_code: str = Field(min_length=1, max_length=80)
    status: str = Field(pattern="^(trialing|active|past_due|cancelled)$")


class SupportAccessCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=10, max_length=1000)
    permissions: list[str] = Field(min_length=1, max_length=20)
    expires_in_minutes: int = Field(ge=1, le=60)
    approved_by_user_id: UUID | None = None

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, values: list[str]) -> list[str]:
        return [validate_permission_code(value) for value in values]


class PrivacyRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_type: str = Field(pattern="^(access|correction|deletion|restriction)$")
    reason: str = Field(min_length=1, max_length=1000)


class PrivacyRequestResolve(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_status: str = Field(pattern="^(requested|in_review|approved|rejected|completed)$")
    status: str = Field(pattern="^(in_review|approved|rejected|completed)$")
    resolution_note: str | None = Field(default=None, max_length=2000)


class PrivacyIdentityVerify(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_note: str = Field(min_length=5, max_length=500)


class ExportJobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    export_type: str = Field(pattern="^(patient_access|audit)$")
    patient_id: UUID | None = None
    privacy_request_id: UUID | None = None


class PlanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=80, pattern="^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=160)
    limits: dict[str, int | None] = Field(default_factory=dict, max_length=50)


class PlanLimitUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit_value: int | None = Field(default=None, ge=0)
    enabled: bool = True


class AnnouncementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)
    severity: str = Field(default="info", pattern="^(info|warning|critical)$")
    ends_at: str | None = Field(default=None, max_length=40)
