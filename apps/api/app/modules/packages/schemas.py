from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PackageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    specialty_id: UUID | None = None
    total_price_minor: int = Field(ge=0)
    original_value_minor: int | None = Field(default=None, ge=0)
    currency: str = Field(min_length=3, max_length=3)
    validity_days: int = Field(gt=0, le=3650)


class PackageServiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_id: UUID
    sessions_count: int = Field(gt=0, le=1000)


class PackagePurchase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: UUID
    invoice_id: UUID | None = None


class PackageConsume(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_id: UUID | None = None
    appointment_id: UUID | None = None
    override_reason: str | None = Field(default=None, max_length=500)
