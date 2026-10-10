from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PatientCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    date_of_birth: date | None = None
    emergency_contact_name: str | None = Field(default=None, max_length=200)
    emergency_contact_phone: str | None = Field(default=None, max_length=40)
    emergency_contact_relation: str | None = Field(default=None, max_length=80)
    preferred_communication: str | None = Field(default=None, pattern="^(phone|email|sms|whatsapp)$")
    contraindications: str | None = Field(default=None, max_length=2000)
    allergies_summary: str | None = Field(default=None, max_length=2000)


class PatientUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    date_of_birth: date | None = None
    emergency_contact_name: str | None = Field(default=None, max_length=200)
    emergency_contact_phone: str | None = Field(default=None, max_length=40)
    emergency_contact_relation: str | None = Field(default=None, max_length=80)
    preferred_communication: str | None = Field(default=None, pattern="^(phone|email|sms|whatsapp)$")
    contraindications: str | None = Field(default=None, max_length=2000)
    allergies_summary: str | None = Field(default=None, max_length=2000)


class ContactCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_type: str = Field(min_length=1, max_length=40)
    value: str = Field(min_length=1, max_length=320)
    is_primary: bool = False


class TagCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)


class PatientMerge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_patient_id: UUID
    reason: str = Field(min_length=1, max_length=500)


class PatientNoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=10000)
    note_type: str = Field(default="general", min_length=1, max_length=40)
    visibility: str = Field(default="clinic", pattern="^(clinic|care_team|private_doctor)$")


class PatientNoteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    body: str | None = Field(default=None, min_length=1, max_length=10000)
    note_type: str | None = Field(default=None, min_length=1, max_length=40)
    visibility: str | None = Field(default=None, pattern="^(clinic|care_team|private_doctor)$")

    @model_validator(mode="after")
    def requires_a_change(self):
        if self.body is None and self.note_type is None and self.visibility is None:
            raise ValueError("at least one note field must be provided")
        return self


class ConsentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    consent_type: str = Field(min_length=1, max_length=80)
    status: str = Field(pattern="^(granted|withdrawn|declined)$")
    version: str = Field(min_length=1, max_length=40)


class ConsentRevoke(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class CareTeamMemberCreate(BaseModel):
    """Explicitly assign an active doctor to a patient care team."""

    model_config = ConfigDict(extra="forbid")

    doctor_id: UUID


class CareTeamPolicyUpdate(BaseModel):
    """A versioned, fail-closed policy for manager care-team-note access.

    Version zero represents the implicit default (no persisted policy row and
    managers cannot read care-team notes).
    """

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0)
    allow_manager_care_team_notes: bool


class TransferCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_branch_id: UUID
    to_branch_id: UUID
    from_doctor_id: UUID | None = None
    to_doctor_id: UUID | None = None
    reason: str = Field(min_length=1, max_length=1000)
    notes: str | None = Field(default=None, max_length=2000)


class DischargeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_id: UUID
    discharge_type: str = Field(default="regular", pattern="^(regular|against_advice|referral|transfer)$")
    diagnosis: str | None = Field(default=None, max_length=2000)
    treatment_summary: str | None = Field(default=None, max_length=4000)
    discharge_instructions: str | None = Field(default=None, max_length=4000)
    follow_up_required: bool = False
    follow_up_date: date | None = None


class AdmissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_id: UUID
    admitting_doctor_id: UUID
    consulting_doctor_id: UUID | None = None
    ward: str | None = Field(default=None, max_length=100)
    bed: str | None = Field(default=None, max_length=50)
    admission_type: str = Field(default="elective", pattern="^(elective|emergency|transfer|observation)$")
    reason: str = Field(min_length=1, max_length=2000)
    diagnosis_on_admission: str | None = Field(default=None, max_length=2000)
    expected_stay_days: int | None = Field(default=None, ge=1, le=365)
    notes: str | None = Field(default=None, max_length=5000)


class AdmissionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    ward: str | None = Field(default=None, max_length=100)
    bed: str | None = Field(default=None, max_length=50)
    consulting_doctor_id: UUID | None = None
    diagnosis_on_admission: str | None = Field(default=None, max_length=2000)
    expected_stay_days: int | None = Field(default=None, ge=1, le=365)
    notes: str | None = Field(default=None, max_length=5000)


class AdmissionDischarge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class VitalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vital_type: str = Field(max_length=40, pattern="^(blood_pressure|condition|procedure|allergy|temperature|heart_rate|weight|height|note)$")
    label: str | None = Field(default=None, max_length=200)
    value_text: str | None = Field(default=None, max_length=1000)
    value_systolic: int | None = None
    value_diastolic: int | None = None
    value_numeric: float | None = None
    unit: str | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=2000)
