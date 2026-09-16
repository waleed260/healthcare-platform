import pytest

from app.modules.appointments.state import validate_transition
from app.modules.appointments.schemas import AppointmentAssignRequest, BookingAnswer, PublicBookingRequest


def test_appointment_state_machine_accepts_expected_flow() -> None:
    for current, target in (("requested", "confirmed"), ("confirmed", "arrived"), ("arrived", "waiting"), ("waiting", "in_consultation"), ("in_consultation", "completed")):
        validate_transition(current, target)


def test_appointment_state_machine_rejects_skips() -> None:
    with pytest.raises(ValueError):
        validate_transition("requested", "completed")


def test_public_booking_answers_are_strict_and_bounded() -> None:
    payload = PublicBookingRequest(
        branch_id="00000000-0000-0000-0000-000000000001",
        service_id="00000000-0000-0000-0000-000000000002",
        starts_at="2026-09-15T10:00:00+00:00",
        full_name="Synthetic Patient",
        answers=[BookingAnswer(question_id="00000000-0000-0000-0000-000000000003", value="yes")],
    )
    assert payload.answers[0].value == "yes"


def test_assignment_requires_optimistic_version() -> None:
    with pytest.raises(ValueError):
        AppointmentAssignRequest(doctor_id="00000000-0000-0000-0000-000000000003")
