from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.authorization.permissions import PERMISSIONS, validate_permission_code


def test_permission_catalog_rejects_unknown_codes() -> None:
    assert validate_permission_code("clinic.read") == "clinic.read"
    assert {"patient.private_note.read", "appointment.reschedule", "admin.support.access"}.issubset(PERMISSIONS)
    with pytest.raises(ValueError):
        validate_permission_code("patients.read.all")


def test_production_configuration_fails_closed_without_secrets() -> None:
    with pytest.raises(ValueError, match="SESSION_HMAC_KEY"):
        Settings(app_env="production")


def test_storage_backend_is_allowlisted() -> None:
    with pytest.raises(ValueError, match="STORAGE_BACKEND"):
        Settings(storage_backend="filesystem")


def test_uuid_generation_is_available_for_scope_fixtures() -> None:
    assert uuid4() != uuid4()
