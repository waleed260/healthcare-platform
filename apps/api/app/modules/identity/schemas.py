from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=256)


class SessionRevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID


class ManualResetConsumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=20, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class MfaVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=6, max_length=16)


class MfaRecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=8, max_length=32)


class InvitationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=160)


class InvitationConsumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=20, max_length=256)
    password: str = Field(min_length=12, max_length=256)
    display_name: str = Field(min_length=1, max_length=160)


class MfaEnrollResponse(BaseModel):
    secret: str
    recovery_codes: list[str]
