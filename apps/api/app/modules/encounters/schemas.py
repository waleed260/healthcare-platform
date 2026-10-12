from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


EncounterType = Literal["general", "emergency", "dental", "dermatology", "hair", "skin", "follow_up", "procedure"]
EncounterStatus = Literal["draft", "in_progress", "ready_for_discharge", "discharged", "finalized", "referred", "transferred"]
AllergyStatus = Literal["unknown", "none_known", "has_allergies"]
DischargeOutcome = Literal["home", "referral", "transfer", "against_advice", "admitted"]


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


class AdministeredTreatment(BaseModel):
    name: str = Field(max_length=200)
    dosage: str | None = Field(default=None, max_length=100)
    route: str | None = Field(default=None, max_length=60)
    administered_at: str | None = Field(default=None, max_length=30)
    administered_by: str | None = Field(default=None, max_length=200)
    response: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=500)


class AdministeredProcedure(BaseModel):
    name: str = Field(max_length=200)
    performed_at: str | None = Field(default=None, max_length=30)
    performer: str | None = Field(default=None, max_length=200)
    findings: str | None = Field(default=None, max_length=2000)
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
    arrival_mode: str | None = Field(default=None, max_length=60)
    arrival_datetime: datetime | None = None
    attendant_name: str | None = Field(default=None, max_length=200)
    attendant_phone: str | None = Field(default=None, max_length=30)
    condition_on_arrival: str | None = Field(default=None, max_length=2000)


class EncounterUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    # Assessment
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
    # Arrival
    arrival_mode: str | None = Field(default=None, max_length=60)
    arrival_datetime: datetime | None = None
    attendant_name: str | None = Field(default=None, max_length=200)
    attendant_phone: str | None = Field(default=None, max_length=30)
    condition_on_arrival: str | None = Field(default=None, max_length=2000)
    # Clinical
    known_allergies: str | None = Field(default=None, max_length=2000)
    allergy_status: AllergyStatus | None = None
    medical_history: str | None = Field(default=None, max_length=10000)
    current_medications_text: str | None = Field(default=None, max_length=5000)
    symptom_duration: str | None = Field(default=None, max_length=200)
    gcs_eye: int | None = Field(default=None, ge=1, le=4)
    gcs_verbal: int | None = Field(default=None, ge=1, le=5)
    gcs_motor: int | None = Field(default=None, ge=1, le=6)
    pain_score: int | None = Field(default=None, ge=0, le=10)
    investigation_results: str | None = Field(default=None, max_length=10000)
    clinical_assessment: str | None = Field(default=None, max_length=10000)
    # Administered
    administered_treatments: list[AdministeredTreatment] | None = None
    administered_procedures: list[AdministeredProcedure] | None = None
    treatment_response: str | None = Field(default=None, max_length=5000)
    adverse_reactions: str | None = Field(default=None, max_length=5000)
    # Discharge
    discharge_condition: str | None = Field(default=None, max_length=2000)
    discharge_outcome: DischargeOutcome | None = None
    discharge_destination: str | None = Field(default=None, max_length=500)
    discharge_reason: str | None = Field(default=None, max_length=2000)
    discharge_instructions: str | None = Field(default=None, max_length=5000)
    warning_signs: str | None = Field(default=None, max_length=2000)
    medicine_guidance: str | None = Field(default=None, max_length=5000)
    follow_up_clinician: str | None = Field(default=None, max_length=200)
    follow_up_department: str | None = Field(default=None, max_length=200)
    referral_instructions: str | None = Field(default=None, max_length=5000)


class EncounterStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    status: EncounterStatus


class EncounterDischarge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    discharge_condition: str | None = Field(default=None, max_length=2000)
    discharge_outcome: DischargeOutcome
    discharge_destination: str | None = Field(default=None, max_length=500)
    discharge_reason: str | None = Field(default=None, max_length=2000)
    discharge_notes: str | None = Field(default=None, max_length=5000)
    discharge_instructions: str | None = Field(default=None, max_length=5000)
    warning_signs: str | None = Field(default=None, max_length=2000)
    medicine_guidance: str | None = Field(default=None, max_length=5000)
    follow_up_date: date | None = None
    follow_up_instructions: str | None = Field(default=None, max_length=5000)
    follow_up_clinician: str | None = Field(default=None, max_length=200)
    follow_up_department: str | None = Field(default=None, max_length=200)
    referral_instructions: str | None = Field(default=None, max_length=5000)
    discharge_vitals: VitalsEntry | None = None


class EncounterAmendment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    field: str = Field(max_length=100)
    old_value: str | None = Field(default=None, max_length=10000)
    new_value: str = Field(max_length=10000)
    reason: str = Field(min_length=1, max_length=2000)
