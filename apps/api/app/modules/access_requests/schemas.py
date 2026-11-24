from pydantic import BaseModel, ConfigDict, Field


class AccessRequestCreate(BaseModel):
    """Public self-service access request. The requester supplies only a hint of
    the role/reason; the administrator decides the actual role on approval."""

    model_config = ConfigDict(extra="forbid")

    clinic_slug: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=320)
    display_name: str | None = Field(default=None, max_length=200)
    requested_role: str | None = Field(default=None, max_length=100)
    reason: str | None = Field(default=None, max_length=1000)


class AccessRequestApprove(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    role_name: str = Field(min_length=1, max_length=100)


class AccessRequestReject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=1000)
