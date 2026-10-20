from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InventoryCategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]*$")
    display_order: int = Field(default=0, ge=0, le=9999)


class InventoryCategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    slug: str | None = Field(default=None, min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]*$")
    display_order: int | None = Field(default=None, ge=0, le=9999)


class InventoryProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    sku: str | None = Field(default=None, max_length=80)
    product_type: Literal["product", "medicine", "consumable", "material"] | None = None
    unit: str = Field(default="unit", min_length=1, max_length=40)
    minimum_stock: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=3)
    category_id: UUID | None = None
    cost_minor: int | None = Field(default=None, ge=0)
    selling_price_minor: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    tax_inclusive: bool = False


class InventoryProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    sku: str | None = Field(default=None, max_length=80)
    unit: str | None = Field(default=None, min_length=1, max_length=40)
    minimum_stock: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=3)
    category_id: UUID | None = Field(default=None)
    cost_minor: int | None = Field(default=None, ge=0)
    selling_price_minor: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    tax_inclusive: bool | None = Field(default=None)


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
