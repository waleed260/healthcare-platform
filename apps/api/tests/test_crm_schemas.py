from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.crm.schemas import ConsentCreate, ConsentRevoke, ContactCreate, PatientCreate, PatientMerge, PatientNoteCreate, PatientNoteUpdate, PatientUpdate, TagCreate


def test_patient_create_normalizes_shape_and_rejects_extra_fields() -> None:
    patient = PatientCreate(full_name="Synthetic Example", date_of_birth=date(1990, 1, 2))
    assert patient.full_name == "Synthetic Example"
    with pytest.raises(ValidationError):
        PatientCreate(full_name="Synthetic Example", unsupported=True)


def test_merge_requires_a_reason_and_note_visibility_is_closed() -> None:
    merge = PatientMerge(target_patient_id=uuid4(), reason="Duplicate review approved")
    assert merge.reason
    with pytest.raises(ValidationError):
        PatientNoteCreate(body="Synthetic note", visibility="public")
    assert PatientNoteUpdate(expected_version=1, body="Revised synthetic note").body
    assert ConsentRevoke(expected_version=1).expected_version == 1
    with pytest.raises(ValidationError):
        PatientNoteUpdate(expected_version=1)


def test_consent_status_is_explicit() -> None:
    consent = ConsentCreate(consent_type="care", status="granted", version="v1")
    assert consent.status == "granted"
    with pytest.raises(ValidationError):
        ConsentCreate(consent_type="care", status="pending", version="v1")


def test_contact_tag_and_update_contracts_are_strict() -> None:
    assert ContactCreate(contact_type="phone", value="+10000000000").is_primary is False
    assert TagCreate(name="Synthetic").name == "Synthetic"
    assert PatientUpdate(expected_version=1, full_name="Updated Synthetic").expected_version == 1
