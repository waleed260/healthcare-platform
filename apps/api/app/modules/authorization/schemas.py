from pydantic import BaseModel, ConfigDict, Field


class ClinicUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)
    timezone: str | None = Field(default=None, min_length=1, max_length=80)
    locale: str | None = Field(default=None, pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$", max_length=10)


class ClinicStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    status: str = Field(pattern="^(active|suspended|archived)$")
