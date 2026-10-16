from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StaffInvitationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)


class StaffStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    status: str = Field(pattern="^(active|suspended|deactivated)$")


class ManualResetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=500)


class RoleAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_id: UUID


class RoleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    permissions: list[str] = Field(default_factory=list, max_length=200)


class RoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    permissions: list[str] | None = Field(default=None, max_length=200)


class BranchScopeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_id: UUID
