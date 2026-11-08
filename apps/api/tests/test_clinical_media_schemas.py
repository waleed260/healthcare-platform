import pytest
from pydantic import ValidationError

from app.modules.clinical_media.schemas import PatientMediaApproval, PatientMediaCreate


def test_patient_media_create_defaults_to_other() -> None:
    payload = PatientMediaCreate()
    assert payload.media_kind == "other"
    assert payload.captured_on is None


def test_patient_media_create_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        PatientMediaCreate(media_kind="portrait")


def test_patient_media_create_accepts_clinical_kinds_and_metadata() -> None:
    payload = PatientMediaCreate(media_kind="xray", title="Right-knee lateral", notes="Pre-op reference")
    assert payload.media_kind == "xray"
    assert payload.title == "Right-knee lateral"
    assert payload.notes == "Pre-op reference"


def test_patient_media_create_enforces_title_length() -> None:
    with pytest.raises(ValidationError):
        PatientMediaCreate(title="x" * 201)


def test_patient_media_approval_requires_consent() -> None:
    with pytest.raises(ValidationError):
        PatientMediaApproval(expected_version=1)
