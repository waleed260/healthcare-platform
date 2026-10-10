from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


EncounterType = Literal["general", "emergency", "dental", "dermatology", "hair", "skin", "follow_up", "procedure"]
EncounterStatus = Literal["draft", "in_review", "finalized"]


class MedicationEntry(BaseModel):
    name: str = Field(max_length=200)
    dosage: str | None = Field(default=None, max_length=100)
    route: str | None = Field(default=None, max_length=60)
    frequency: str | None = Field(default=None, max_length=100)
    duration: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=500)


class VitalsEntry(BaseModel):
    blood_pressure: str | None = Field(default=None, max_length=20)
    pulse: int | None = Field(default=None, ge=0, le=300)
    temperature: float | None = Field(default=None, ge=30, le=45)
    respiratory_rate: int | None = Field(default=None, ge=0, le=100)
    oxygen_saturation: int | None = Field(default=None, ge=0, le=100)
    weight_kg: float | None = Field(default=None, ge=0, le=500)
    height_cm: float | None = Field(default=None, ge=0, le=300)
    notes: str | None = Field(default=None, max_length=500)


class EncounterCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: UUID
    appointment_id: UUID | None = None
    doctor_id: UUID
    branch_id: UUID | None = None
    encounter_type: EncounterType = "general"
    chief_complaint: str | None = Field(default=None, max_length=5000)
    arrival_vitals: VitalsEntry | None = None


class EncounterUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    chief_complaint: str | None = Field(default=None, max_length=5000)
    history_present_illness: str | None = Field(default=None, max_length=10000)
    examination_findings: str | None = Field(default=None, max_length=10000)
    diagnosis: str | None = Field(default=None, max_length=5000)
    investigations: str | None = Field(default=None, max_length=5000)
    treatment_plan: str | None = Field(default=None, max_length=5000)
    medications: list[MedicationEntry] | None = None
    procedures_performed: str | None = Field(default=None, max_length=5000)
    follow_up_instructions: str | None = Field(default=None, max_length=5000)
    follow_up_date: date | None = None
    arrival_vitals: VitalsEntry | None = None
    discharge_vitals: VitalsEntry | None = None
    discharge_notes: str | None = Field(default=None, max_length=5000)
    internal_notes: str | None = Field(default=None, max_length=5000)


class EncounterStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    status: EncounterStatus
