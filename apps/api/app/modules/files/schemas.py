from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_filename: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=100)
    size_bytes: int = Field(gt=0, le=20 * 1024 * 1024)
    content_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


class DocumentAccess(BaseModel):
    document_id: UUID
    expires_at: int
    access_token: str
