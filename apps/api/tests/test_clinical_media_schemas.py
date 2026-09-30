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


def test_patient_media_approval_requires_consent() -> None:
    with pytest.raises(ValidationError):
        PatientMediaApproval(expected_version=1)
