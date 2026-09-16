from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StaffInvitationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)


class StaffStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    status: str = Field(pattern="^(active|suspended|deactivated)$")


class RoleAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_id: UUID


class BranchScopeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_id: UUID
