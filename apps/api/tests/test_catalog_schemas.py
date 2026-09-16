import pytest
from pydantic import ValidationError

from app.modules.catalog.schemas import BranchUpdate, DoctorUpdate, ServiceCreate, ServiceUpdate


def test_service_schema_rejects_invalid_duration() -> None:
    with pytest.raises(ValidationError):
        ServiceCreate(name="Synthetic", duration_minutes=0)


def test_service_schema_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ServiceCreate(name="Synthetic", duration_minutes=30, arbitrary_html="<script>")


def test_branch_update_requires_version_and_a_change() -> None:
    assert BranchUpdate(expected_version=2, name="Synthetic Updated Clinic").expected_version == 2

    with pytest.raises(ValidationError):
        BranchUpdate(expected_version=2)


def test_service_update_requires_version_and_a_change() -> None:
    assert ServiceUpdate(expected_version=3, duration_minutes=45).duration_minutes == 45

    with pytest.raises(ValidationError):
        ServiceUpdate(expected_version=3)


def test_doctor_update_requires_version_and_a_change() -> None:
    assert DoctorUpdate(expected_version=4, public_name="Synthetic Doctor").expected_version == 4

    with pytest.raises(ValidationError):
        DoctorUpdate(expected_version=4)
