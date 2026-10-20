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


# ── Suppliers ────────────────────────────────────────────────────────────


class SupplierCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    contact_name: str | None = Field(default=None, max_length=160)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    address: dict | None = None
    notes: str | None = Field(default=None, max_length=2000)


class SupplierUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    contact_name: str | None = Field(default=None, max_length=160)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    address: dict | None = None
    notes: str | None = Field(default=None, max_length=2000)


# ── Warehouses ───────────────────────────────────────────────────────────


class WarehouseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    code: str = Field(min_length=1, max_length=40, pattern=r"^[A-Z0-9][A-Z0-9-]*$")
    branch_id: UUID
    warehouse_type: Literal["warehouse", "store", "cold_storage"] = "warehouse"
    contact_name: str | None = Field(default=None, max_length=160)
    contact_phone: str | None = Field(default=None, max_length=40)
    address: dict | None = None


class WarehouseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    code: str | None = Field(default=None, min_length=1, max_length=40, pattern=r"^[A-Z0-9][A-Z0-9-]*$")
    branch_id: UUID | None = None
    warehouse_type: Literal["warehouse", "store", "cold_storage"] | None = None
    contact_name: str | None = Field(default=None, max_length=160)
    contact_phone: str | None = Field(default=None, max_length=40)
    address: dict | None = None


# ── Purchase Orders ──────────────────────────────────────────────────────


class PurchaseOrderLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    quantity_ordered: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    unit_cost_minor: int = Field(ge=0)


class PurchaseOrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_id: UUID
    warehouse_id: UUID
    notes: str | None = Field(default=None, max_length=2000)
    lines: list[PurchaseOrderLineInput] = Field(min_length=1, max_length=200)


class PurchaseOrderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    supplier_id: UUID | None = None
    warehouse_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)


class PurchaseOrderReceiveLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_id: UUID
    quantity_received: Decimal = Field(ge=0, max_digits=12, decimal_places=3)


class PurchaseOrderReceive(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    lines: list[PurchaseOrderReceiveLine] = Field(min_length=1, max_length=200)


# ── Transfers ────────────────────────────────────────────────────────────


class TransferLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    quantity_sent: Decimal = Field(gt=0, max_digits=12, decimal_places=3)


class TransferCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_warehouse_id: UUID
    destination_warehouse_id: UUID
    notes: str | None = Field(default=None, max_length=2000)
    lines: list[TransferLineInput] = Field(min_length=1, max_length=200)

    @field_validator("destination_warehouse_id")
    @classmethod
    def different_warehouses(cls, v: UUID, info) -> UUID:
        if info.data.get("source_warehouse_id") == v:
            raise ValueError("source and destination warehouses must be different")
        return v


class TransferHandover(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    driver_name: str = Field(min_length=1, max_length=160)
    driver_phone: str | None = Field(default=None, max_length=40)


class TransferReceiveLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_id: UUID
    quantity_received: Decimal = Field(ge=0, max_digits=12, decimal_places=3)
    condition: Literal["good", "damaged", "short"]
    notes: str | None = Field(default=None, max_length=500)


class TransferReceive(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    lines: list[TransferReceiveLineInput] = Field(min_length=1, max_length=200)


class TransferCancel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)
