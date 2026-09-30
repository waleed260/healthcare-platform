from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SpecialtyEnable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")


class LeadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    source: str = Field(min_length=1, max_length=80)
    campaign: str | None = Field(default=None, max_length=160)
    specialty_id: UUID | None = None
    requested_service_id: UUID | None = None
    assigned_to_user_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=5000)


class LeadUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    status: Literal['new', 'contacted', 'qualified', 'appointment_booked', 'visited', 'lost'] | None = None
    assigned_to_user_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=5000)
    lost_reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_change(self):
        if not any(getattr(self, field) is not None for field in ('status', 'assigned_to_user_id', 'notes', 'lost_reason')):
            raise ValueError('at least one lead field must be supplied')
        return self


class LeadConvert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: UUID | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    date_of_birth: date | None = None


class InvoiceLineCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=500)
    quantity: int = Field(gt=0, le=10000)
    unit_price_minor: int = Field(ge=0)
    tax_minor: int = Field(default=0, ge=0)
    service_id: UUID | None = None


class InvoiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: UUID
    currency: str = Field(min_length=3, max_length=3)
    discount_minor: int = Field(default=0, ge=0)
    notes: str | None = Field(default=None, max_length=2000)
    lines: list[InvoiceLineCreate] = Field(min_length=1, max_length=100)


class PaymentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_minor: int = Field(gt=0)
    method: Literal['cash', 'card', 'bank_transfer', 'online', 'other']
    reference: str | None = Field(default=None, max_length=160)
