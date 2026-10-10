from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    task_type: Literal["general", "follow_up", "callback", "review", "billing", "clinical", "admin"] = "general"
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    assignee_user_id: UUID | None = None
    patient_id: UUID | None = None
    lead_id: UUID | None = None
    appointment_id: UUID | None = None
    due_at: AwareDatetime | None = None


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    status: Literal["open", "in_progress", "completed", "cancelled"] | None = None
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    assignee_user_id: UUID | None = None
    due_at: AwareDatetime | None = None
