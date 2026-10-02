from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExpenseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category: Literal["rent", "salaries", "utilities", "supplies", "equipment", "marketing", "maintenance", "other"]
    description: str = Field(min_length=1, max_length=500)
    amount_minor: int = Field(gt=0, le=10_000_000_000)
    currency: str = Field(default="PKR", min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    incurred_on: date
    branch_id: UUID | None = None


class ExpenseVoid(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str = Field(min_length=3, max_length=300)


class CommissionRuleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    percent_bp: int = Field(ge=0, le=10000)
    active: bool = True
