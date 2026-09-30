from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InventoryProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    sku: str | None = Field(default=None, max_length=80)
    product_type: Literal["product", "medicine", "consumable", "material"]
    unit: str = Field(default="unit", min_length=1, max_length=40)
    minimum_stock: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=3)


class InventoryProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    sku: str | None = Field(default=None, max_length=80)
    unit: str | None = Field(default=None, min_length=1, max_length=40)
    minimum_stock: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=3)


class InventoryStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "archived"]


class InventoryAdjustmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_id: UUID
    product_id: UUID
    delta: Decimal = Field(max_digits=12, decimal_places=3)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("delta")
    @classmethod
    def non_zero_delta(cls, value: Decimal) -> Decimal:
        if value == 0:
            raise ValueError("delta must not be zero")
        return value
