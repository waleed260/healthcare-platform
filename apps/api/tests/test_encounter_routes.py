"""Unit tests for encounter route-level logic (no DB required)."""
import json
import pytest

from app.modules.encounters.routes import (
    ALLOWED_TRANSITIONS,
    ALL_ENCOUNTER_COLUMNS,
    RETURNING_COLUMNS,
    JSONB_FIELDS,
    DATETIME_FIELDS,
    _serialize_jsonb,
)
from app.modules.encounters.schemas import (
    AdministeredTreatment,
    MedicationEntry,
    VitalsEntry,
)


class TestAllowedTransitions:
    def test_draft_transitions(self):
        assert ALLOWED_TRANSITIONS["draft"] == {"in_progress"}

    def test_in_progress_transitions(self):
        assert ALLOWED_TRANSITIONS["in_progress"] == {"ready_for_discharge", "referred", "transferred"}

    def test_ready_for_discharge_transitions(self):
        assert ALLOWED_TRANSITIONS["ready_for_discharge"] == {"discharged", "in_progress"}

    def test_discharged_transitions(self):
        assert ALLOWED_TRANSITIONS["discharged"] == {"finalized"}

    def test_finalized_has_no_transitions(self):
        assert "finalized" not in ALLOWED_TRANSITIONS

    def test_no_backwards_from_finalized(self):
        for targets in ALLOWED_TRANSITIONS.values():
            assert "draft" not in targets


class TestColumnConstants:
    def test_all_encounter_columns_are_aliased(self):
        for col in ALL_ENCOUNTER_COLUMNS.split(","):
            col = col.strip()
            assert col.startswith("e."), f"Column '{col}' missing table alias"

    def test_returning_columns_are_unaliased(self):
        for col in RETURNING_COLUMNS.split(","):
            col = col.strip()
            assert not col.startswith("e."), f"RETURNING column '{col}' should not have alias"

    def test_same_column_set(self):
        aliased = {c.strip().removeprefix("e.") for c in ALL_ENCOUNTER_COLUMNS.split(",")}
        unaliased = {c.strip() for c in RETURNING_COLUMNS.split(",")}
        assert aliased == unaliased


class TestJsonbSerialization:
    def test_medications_serialization(self):
        meds = [MedicationEntry(name="Aspirin", dosage="100mg")]
        result = _serialize_jsonb("medications", meds)
        parsed = json.loads(result)
        assert len(parsed) == 1
        assert parsed[0]["name"] == "Aspirin"

    def test_vitals_serialization(self):
        vitals = VitalsEntry(pulse=72, blood_pressure="120/80")
        result = _serialize_jsonb("arrival_vitals", vitals)
        parsed = json.loads(result)
        assert parsed["pulse"] == 72

    def test_administered_treatments_serialization(self):
        treatments = [AdministeredTreatment(name="Saline", route="IV")]
        result = _serialize_jsonb("administered_treatments", treatments)
        parsed = json.loads(result)
        assert parsed[0]["route"] == "IV"

    def test_none_returns_none(self):
        assert _serialize_jsonb("medications", None) is None


class TestFieldSets:
    def test_jsonb_fields_are_known(self):
        expected = {"medications", "arrival_vitals", "discharge_vitals", "administered_treatments", "administered_procedures"}
        assert JSONB_FIELDS == expected

    def test_datetime_fields_are_known(self):
        assert DATETIME_FIELDS == {"arrival_datetime"}
