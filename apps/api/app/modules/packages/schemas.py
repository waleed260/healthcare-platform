from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PackageServiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_id: UUID
    sessions_count: int = Field(gt=0, le=1000)


class PackageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    specialty_id: UUID | None = None
    total_price_minor: int = Field(ge=0)
    original_value_minor: int | None = Field(default=None, ge=0)
    currency: str = Field(min_length=3, max_length=3)
    validity_days: int = Field(gt=0, le=3650)
    # Optional at the API level (existing callers create the shell first); the UI sends the
    # included services so a new package is immediately sellable instead of rejecting the sale.
    services: list[PackageServiceCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def _original_not_below_price(self):
        if self.original_value_minor is not None and self.original_value_minor < self.total_price_minor:
            raise ValueError("original_value_minor cannot be below total_price_minor")
        return self


class PackageUpdate(BaseModel):
    """Edit a package definition. Only provided fields change; validity/price edits
    affect future sales only — existing purchases keep their purchase-time entitlements."""
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    specialty_id: UUID | None = None
    total_price_minor: int | None = Field(default=None, ge=0)
    original_value_minor: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    validity_days: int | None = Field(default=None, gt=0, le=3650)
    expected_version: int = Field(ge=1)

    @model_validator(mode="after")
    def _at_least_one_change(self):
        if not any(getattr(self, f) is not None for f in (
            "name", "description", "specialty_id", "total_price_minor",
            "original_value_minor", "currency", "validity_days",
        )):
            raise ValueError("provide at least one field to update")
        return self


class PackageStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["activate", "deactivate", "archive", "unarchive"]
    expected_version: int = Field(ge=1)


class PackagePayment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_minor: int = Field(gt=0)
    method: Literal["cash", "card", "bank_transfer", "online", "other"]
    reference: str | None = Field(default=None, max_length=160)


class PackagePurchase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: UUID
    invoice_id: UUID | None = None
    idempotency_key: UUID | None = None
    create_invoice: bool = False
    payment: PackagePayment | None = None

    @model_validator(mode="after")
    def _billing_consistency(self):
        if self.create_invoice and self.invoice_id is not None:
            raise ValueError("provide either invoice_id (to link) or create_invoice, not both")
        if self.payment is not None and not self.create_invoice and self.invoice_id is None:
            raise ValueError("recording a payment requires create_invoice or an invoice_id")
        return self


class PackageConsume(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_id: UUID | None = None
    appointment_id: UUID | None = None
    override_reason: str | None = Field(default=None, max_length=500)
