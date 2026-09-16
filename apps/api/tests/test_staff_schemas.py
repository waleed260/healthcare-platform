import pytest
from pydantic import ValidationError

from app.modules.staff.schemas import StaffStatusUpdate


def test_staff_status_requires_optimistic_version() -> None:
    with pytest.raises(ValidationError):
        StaffStatusUpdate(status="deactivated")


def test_staff_status_rejects_unknown_state() -> None:
    with pytest.raises(ValidationError):
        StaffStatusUpdate(expected_version=1, status="deleted")
