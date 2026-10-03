"""Unit coverage for CRM route helpers that need no database."""
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.modules.crm import routes
from app.modules.crm.routes import _raise_write_integrity
from app.modules.crm.schemas import CareTeamPolicyUpdate


def _integrity(sqlstate: str) -> IntegrityError:
    return IntegrityError("INSERT INTO ...", {}, SimpleNamespace(sqlstate=sqlstate))


def test_foreign_key_violation_maps_to_404() -> None:
    # L4: a missing patient (FK 23503) is a genuine 404.
    with pytest.raises(HTTPException) as error:
        _raise_write_integrity(_integrity("23503"), duplicate_message="This contact already exists.")
    assert error.value.status_code == 404
    assert error.value.detail["error"]["code"] == "NOT_FOUND"


def test_unique_violation_maps_to_409_not_404() -> None:
    # L4: a unique violation (23505) is a duplicate → 409, not a blanket 404.
    with pytest.raises(HTTPException) as error:
        _raise_write_integrity(_integrity("23505"), duplicate_message="This contact already exists for the patient.")
    assert error.value.status_code == 409
    assert error.value.detail["error"]["code"] == "DUPLICATE"
    assert error.value.detail["error"]["message"] == "This contact already exists for the patient."


def test_unexpected_constraint_is_reraised_as_500() -> None:
    # L4: any other constraint is unexpected and surfaces (as a 500) rather than
    # being mislabelled 'Patient not found'.
    original = _integrity("23502")  # NOT NULL — not something these routes map
    with pytest.raises(IntegrityError) as error:
        _raise_write_integrity(original, duplicate_message="dup")
    assert error.value is original


def test_care_policy_first_write_race_loser_gets_409(monkeypatch) -> None:
    """L6: when two version-0 writers both read no row and both INSERT, the loser
    hits the clinic_id PK. The handler converts that IntegrityError into a 409
    VERSION_CONFLICT (the schema's fail-closed version-0 contract) instead of 500."""
    session = {"clinic_id": uuid4(), "user_id": uuid4()}
    request = SimpleNamespace(state=SimpleNamespace(request_id=str(uuid4())))
    monkeypatch.setattr(routes, "_write_authorized", lambda *args, **kwargs: session)
    audit = Mock()
    monkeypatch.setattr(routes, "record_event", audit)

    db = Mock()
    db.execute.side_effect = [
        Mock(scalar_one_or_none=lambda: None),  # no existing policy row (version 0)
        _integrity("23505"),  # the INSERT loses the PK race
    ]
    with pytest.raises(HTTPException) as error:
        routes.care_team_policy_update(
            CareTeamPolicyUpdate(expected_version=0, allow_manager_care_team_notes=True),
            request, db, "session", "csrf",
        )
    assert error.value.status_code == 409
    assert error.value.detail["error"]["code"] == "VERSION_CONFLICT"
    db.rollback.assert_called_once()
    audit.assert_not_called()
    db.commit.assert_not_called()
