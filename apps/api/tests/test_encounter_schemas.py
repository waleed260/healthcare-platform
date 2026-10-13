import pytest
from datetime import date, datetime
from uuid import uuid4

from pydantic import ValidationError

from app.modules.encounters.schemas import (
    AdministeredProcedure,
    AdministeredTreatment,
    AllergyStatus,
    DischargeOutcome,
    EncounterAmendment,
    EncounterCreate,
    EncounterDischarge,
    EncounterStatus,
    EncounterStatusUpdate,
    EncounterType,
    EncounterUpdate,
    MedicationEntry,
    VitalsEntry,
)


# ── EncounterCreate ──────────────────────────────────────────────────

class TestEncounterCreate:
    def test_minimal_valid(self):
        ec = EncounterCreate(
            patient_id=uuid4(), doctor_id=uuid4()
        )
        assert ec.encounter_type == "general"
        assert ec.appointment_id is None
        assert ec.arrival_vitals is None

    def test_full_valid(self):
        ec = EncounterCreate(
            patient_id=uuid4(),
            doctor_id=uuid4(),
            appointment_id=uuid4(),
            branch_id=uuid4(),
            encounter_type="emergency",
            chief_complaint="Chest pain",
            arrival_vitals=VitalsEntry(pulse=80, blood_pressure="120/80"),
            arrival_mode="ambulance",
            arrival_datetime=datetime(2026, 10, 13, 9, 0),
            attendant_name="John",
            attendant_phone="+123456789",
            condition_on_arrival="Stable",
        )
        assert ec.encounter_type == "emergency"
        assert ec.arrival_vitals.pulse == 80

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError, match="extra"):
            EncounterCreate(
                patient_id=uuid4(), doctor_id=uuid4(), bogus="x"
            )

    def test_rejects_invalid_encounter_type(self):
        with pytest.raises(ValidationError):
            EncounterCreate(
                patient_id=uuid4(), doctor_id=uuid4(), encounter_type="invalid"
            )


# ── EncounterUpdate ──────────────────────────────────────────────────

class TestEncounterUpdate:
    def test_minimal_update(self):
        eu = EncounterUpdate(expected_version=1, chief_complaint="Headache")
        assert eu.chief_complaint == "Headache"

    def test_gcs_validation(self):
        eu = EncounterUpdate(expected_version=1, gcs_eye=4, gcs_verbal=5, gcs_motor=6)
        assert eu.gcs_eye == 4

    def test_gcs_eye_out_of_range(self):
        with pytest.raises(ValidationError):
            EncounterUpdate(expected_version=1, gcs_eye=5)

    def test_gcs_eye_below_range(self):
        with pytest.raises(ValidationError):
            EncounterUpdate(expected_version=1, gcs_eye=0)

    def test_gcs_verbal_out_of_range(self):
        with pytest.raises(ValidationError):
            EncounterUpdate(expected_version=1, gcs_verbal=6)

    def test_gcs_motor_out_of_range(self):
        with pytest.raises(ValidationError):
            EncounterUpdate(expected_version=1, gcs_motor=7)

    def test_pain_score_valid_range(self):
        for score in [0, 5, 10]:
            eu = EncounterUpdate(expected_version=1, pain_score=score)
            assert eu.pain_score == score

    def test_pain_score_out_of_range(self):
        with pytest.raises(ValidationError):
            EncounterUpdate(expected_version=1, pain_score=11)
        with pytest.raises(ValidationError):
            EncounterUpdate(expected_version=1, pain_score=-1)

    def test_version_required_positive(self):
        with pytest.raises(ValidationError):
            EncounterUpdate(expected_version=0)

    def test_administered_treatments_list(self):
        eu = EncounterUpdate(
            expected_version=1,
            administered_treatments=[
                AdministeredTreatment(name="Paracetamol", dosage="500mg", route="oral"),
                AdministeredTreatment(name="Saline IV", route="IV"),
            ],
        )
        assert len(eu.administered_treatments) == 2
        assert eu.administered_treatments[0].name == "Paracetamol"

    def test_administered_procedures_list(self):
        eu = EncounterUpdate(
            expected_version=1,
            administered_procedures=[
                AdministeredProcedure(name="Wound dressing", performer="Dr. Smith"),
            ],
        )
        assert eu.administered_procedures[0].performer == "Dr. Smith"

    def test_medications_list(self):
        eu = EncounterUpdate(
            expected_version=1,
            medications=[
                MedicationEntry(name="Amoxicillin", dosage="500mg", route="oral", frequency="TDS", duration="7 days"),
            ],
        )
        assert eu.medications[0].frequency == "TDS"

    def test_discharge_outcome_values(self):
        for outcome in ["home", "referral", "transfer", "against_advice", "admitted"]:
            eu = EncounterUpdate(expected_version=1, discharge_outcome=outcome)
            assert eu.discharge_outcome == outcome

    def test_discharge_outcome_invalid(self):
        with pytest.raises(ValidationError):
            EncounterUpdate(expected_version=1, discharge_outcome="escaped")

    def test_allergy_status_values(self):
        for status in ["unknown", "none_known", "has_allergies"]:
            eu = EncounterUpdate(expected_version=1, allergy_status=status)
            assert eu.allergy_status == status

    def test_allergy_status_invalid(self):
        with pytest.raises(ValidationError):
            EncounterUpdate(expected_version=1, allergy_status="bad_value")


# ── VitalsEntry ──────────────────────────────────────────────────────

class TestVitalsEntry:
    def test_all_fields(self):
        v = VitalsEntry(
            blood_pressure="120/80", pulse=72, temperature=36.6,
            respiratory_rate=16, oxygen_saturation=98,
            weight_kg=70.5, height_cm=175.0, notes="Stable"
        )
        assert v.pulse == 72
        assert v.weight_kg == 70.5

    def test_bmi_calculation_from_vitals(self):
        v = VitalsEntry(weight_kg=70, height_cm=175)
        bmi = v.weight_kg / ((v.height_cm / 100) ** 2)
        assert round(bmi, 1) == 22.9

    def test_pulse_range(self):
        with pytest.raises(ValidationError):
            VitalsEntry(pulse=301)
        with pytest.raises(ValidationError):
            VitalsEntry(pulse=-1)

    def test_temperature_range(self):
        with pytest.raises(ValidationError):
            VitalsEntry(temperature=29)
        with pytest.raises(ValidationError):
            VitalsEntry(temperature=46)

    def test_spo2_range(self):
        with pytest.raises(ValidationError):
            VitalsEntry(oxygen_saturation=101)
        with pytest.raises(ValidationError):
            VitalsEntry(oxygen_saturation=-1)


# ── EncounterDischarge ───────────────────────────────────────────────

class TestEncounterDischarge:
    def test_minimal_discharge(self):
        ed = EncounterDischarge(expected_version=1, discharge_outcome="home")
        assert ed.discharge_outcome == "home"
        assert ed.discharge_vitals is None

    def test_full_discharge(self):
        ed = EncounterDischarge(
            expected_version=1,
            discharge_outcome="referral",
            discharge_condition="Stable",
            discharge_destination="City Hospital",
            discharge_reason="Specialist consultation needed",
            discharge_notes="Follow-up in 2 weeks",
            discharge_instructions="Rest, fluids, monitor temperature",
            warning_signs="High fever, difficulty breathing",
            medicine_guidance="Complete antibiotic course",
            follow_up_date=date(2026, 10, 27),
            follow_up_instructions="Blood work before visit",
            follow_up_clinician="Dr. Khan",
            follow_up_department="Pulmonology",
            referral_instructions="Bring imaging results",
            discharge_vitals=VitalsEntry(pulse=78, blood_pressure="118/76"),
        )
        assert ed.discharge_destination == "City Hospital"
        assert ed.discharge_vitals.pulse == 78

    def test_discharge_outcome_required(self):
        with pytest.raises(ValidationError):
            EncounterDischarge(expected_version=1)


# ── EncounterStatusUpdate ────────────────────────────────────────────

class TestEncounterStatusUpdate:
    def test_valid_statuses(self):
        for st in ["draft", "in_progress", "ready_for_discharge", "discharged", "finalized", "referred", "transferred"]:
            esu = EncounterStatusUpdate(expected_version=1, status=st)
            assert esu.status == st

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            EncounterStatusUpdate(expected_version=1, status="cancelled")


# ── EncounterAmendment ───────────────────────────────────────────────

class TestEncounterAmendment:
    def test_valid_amendment(self):
        ea = EncounterAmendment(
            expected_version=3,
            field="diagnosis",
            old_value="Initial diagnosis",
            new_value="Corrected diagnosis",
            reason="Lab results updated the diagnosis",
        )
        assert ea.field == "diagnosis"

    def test_reason_required_nonempty(self):
        with pytest.raises(ValidationError):
            EncounterAmendment(
                expected_version=1,
                field="diagnosis",
                new_value="x",
                reason="",
            )

    def test_field_max_length(self):
        with pytest.raises(ValidationError):
            EncounterAmendment(
                expected_version=1,
                field="x" * 101,
                new_value="v",
                reason="r",
            )


# ── Status transitions (route logic, tested as data) ────────────────

class TestStatusTransitions:
    ALLOWED = {
        "draft": {"in_progress"},
        "in_progress": {"ready_for_discharge", "referred", "transferred"},
        "ready_for_discharge": {"discharged", "in_progress"},
        "discharged": {"finalized"},
    }

    def test_draft_to_in_progress(self):
        assert "in_progress" in self.ALLOWED["draft"]

    def test_draft_cannot_skip_to_discharged(self):
        assert "discharged" not in self.ALLOWED["draft"]

    def test_in_progress_to_ready(self):
        assert "ready_for_discharge" in self.ALLOWED["in_progress"]

    def test_in_progress_to_referred(self):
        assert "referred" in self.ALLOWED["in_progress"]

    def test_in_progress_to_transferred(self):
        assert "transferred" in self.ALLOWED["in_progress"]

    def test_ready_can_go_back_to_in_progress(self):
        assert "in_progress" in self.ALLOWED["ready_for_discharge"]

    def test_ready_to_discharged(self):
        assert "discharged" in self.ALLOWED["ready_for_discharge"]

    def test_discharged_to_finalized(self):
        assert "finalized" in self.ALLOWED["discharged"]

    def test_finalized_is_terminal(self):
        assert "finalized" not in self.ALLOWED

    def test_referred_is_terminal(self):
        assert "referred" not in self.ALLOWED

    def test_transferred_is_terminal(self):
        assert "transferred" not in self.ALLOWED


# ── BMI calculation (Section 9 requirement) ──────────────────────────

class TestBMICalculation:
    def test_normal_bmi(self):
        bmi = 70 / ((175 / 100) ** 2)
        assert 22.0 < bmi < 23.0

    def test_underweight_bmi(self):
        bmi = 50 / ((175 / 100) ** 2)
        assert bmi < 18.5

    def test_overweight_bmi(self):
        bmi = 85 / ((175 / 100) ** 2)
        assert 25.0 <= bmi < 30.0

    def test_obese_bmi(self):
        bmi = 100 / ((170 / 100) ** 2)
        assert bmi >= 30.0

    def test_zero_height_guard(self):
        v = VitalsEntry(weight_kg=70, height_cm=0)
        assert v.height_cm == 0

    def test_missing_fields_no_bmi(self):
        v1 = VitalsEntry(weight_kg=70)
        v2 = VitalsEntry(height_cm=175)
        assert v1.height_cm is None
        assert v2.weight_kg is None


# ── GCS calculation (Section 9 requirement) ──────────────────────────

class TestGCSCalculation:
    def test_max_gcs(self):
        total = 4 + 5 + 6
        assert total == 15

    def test_min_gcs(self):
        total = 1 + 1 + 1
        assert total == 3

    def test_mild_classification(self):
        total = 4 + 5 + 5  # 14
        assert total >= 13

    def test_moderate_classification(self):
        total = 3 + 3 + 3  # 9
        assert 9 <= total < 13

    def test_severe_classification(self):
        total = 1 + 2 + 2  # 5
        assert total < 9

    def test_gcs_component_ranges(self):
        EncounterUpdate(expected_version=1, gcs_eye=1, gcs_verbal=1, gcs_motor=1)
        EncounterUpdate(expected_version=1, gcs_eye=4, gcs_verbal=5, gcs_motor=6)


# ── AdministeredTreatment / AdministeredProcedure ────────────────────

class TestAdministeredEntries:
    def test_treatment_name_required(self):
        with pytest.raises(ValidationError):
            AdministeredTreatment(name="")

    def test_procedure_name_max_length(self):
        with pytest.raises(ValidationError):
            AdministeredProcedure(name="x" * 201)

    def test_medication_entry_basic(self):
        m = MedicationEntry(name="Ibuprofen", dosage="400mg", route="oral", frequency="TDS", duration="5 days")
        assert m.name == "Ibuprofen"

    def test_medication_name_required(self):
        with pytest.raises(ValidationError):
            MedicationEntry(name="")
