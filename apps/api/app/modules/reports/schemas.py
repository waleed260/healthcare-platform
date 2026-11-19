from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.reports.registry import SOURCES


class ReportConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    metrics: list[str] = Field(min_length=1, max_length=8)
    group_by: list[str] = Field(default_factory=list, max_length=2)
    filters: dict[str, str] = Field(default_factory=dict)
    range_preset: Literal["7d", "30d", "90d", "180d", "365d", "all"] = "30d"
    start: date | None = None
    end: date | None = None

    @model_validator(mode="after")
    def _validate_against_registry(self):
        src = SOURCES.get(self.source)
        if src is None:
            raise ValueError(f"unknown report source: {self.source}")
        bad = [m for m in self.metrics if m not in src.metrics]
        if bad:
            raise ValueError(f"unknown metric(s) for {self.source}: {', '.join(bad)}")
        bad = [d for d in self.group_by if d not in src.dimensions]
        if bad:
            raise ValueError(f"unknown dimension(s) for {self.source}: {', '.join(bad)}")
        bad = [f for f in self.filters if f not in src.filters]
        if bad:
            raise ValueError(f"unknown filter(s) for {self.source}: {', '.join(bad)}")
        if self.start and self.end and self.end < self.start:
            raise ValueError("end date is before start date")
        return self


class SavedReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    config: ReportConfig


class SavedReportUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    config: ReportConfig | None = None
    expected_version: int = Field(ge=1)

    @model_validator(mode="after")
    def _at_least_one(self):
        if self.name is None and self.description is None and self.config is None:
            raise ValueError("provide at least one field to update")
        return self


class SavedReportDuplicate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
