from uuid import UUID

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.websites.schemas import SectionContent


class ApplySiteTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_key: str = Field(min_length=1, max_length=60)
    expected_version: int = Field(ge=1)
    apply_theme: bool = True


class PageFromTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    template_key: str = Field(min_length=1, max_length=60)
    slug: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    title: str = Field(min_length=1, max_length=160)


class ReusableCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    source_section_id: UUID


class ReusableUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    content: SectionContent | None = None


class ReusableInsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["copy", "synced"] = "copy"


class SectionReorder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_ids: list[UUID] = Field(min_length=1, max_length=100)
