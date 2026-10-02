from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class UpgradeRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: Literal["specialty", "feature", "limit"]
    target_code: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_.-]+$")
    message: str | None = Field(default=None, max_length=1000)


class UpgradeDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decision: Literal["approve", "decline"]
    note: str | None = Field(default=None, max_length=1000)
