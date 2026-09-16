import pytest

from app.modules.audit.service import record_event


def test_audit_metadata_limit_is_checked_before_database_write() -> None:
    with pytest.raises(ValueError):
        record_event(None, clinic_id=None, actor_user_id=None, action="x", entity_type="x", entity_id=None, outcome="failed", metadata={"value": "x" * 17000})
