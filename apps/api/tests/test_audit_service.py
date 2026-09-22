import pytest
from unittest.mock import Mock
from uuid import uuid4

from app.modules.audit.service import record_event


def test_audit_metadata_limit_is_checked_before_database_write() -> None:
    with pytest.raises(ValueError):
        record_event(None, clinic_id=None, actor_user_id=None, action="x", entity_type="x", entity_id=None, outcome="failed", metadata={"value": "x" * 17000})


def test_support_audit_events_persist_the_support_session_link() -> None:
    db = Mock()
    db.execute.return_value.scalar_one.return_value = uuid4()
    support_session_id = uuid4()
    record_event(db, clinic_id=uuid4(), actor_user_id=uuid4(), support_session_id=support_session_id, action="support_access.revoke", entity_type="support_access_session", entity_id=support_session_id, outcome="success")
    assert db.execute.call_args.args[1]["support_session_id"] == support_session_id
