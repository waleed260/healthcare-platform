from datetime import date

import pytest

from app.modules.governance.limits import FeatureLimitExceeded, consume_feature_limit


class _Scalar:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _DB:
    def __init__(self, values):
        self.values = iter(values)
        self.statements = []

    def execute(self, statement, params=None):
        self.statements.append((str(statement), params))
        return _Scalar(next(self.values))


def test_limit_helper_is_noop_when_no_plan_limit_is_configured(monkeypatch) -> None:
    db = _DB([None])
    monkeypatch.setattr("app.modules.governance.limits.set_tenant_context", lambda *args: None)
    consume_feature_limit(db, "clinic", "patient_document_bytes", 100)
    assert len(db.statements) == 1


def test_limit_helper_raises_when_atomic_guard_rejects_increment(monkeypatch) -> None:
    db = _DB([10, None])
    monkeypatch.setattr("app.modules.governance.limits.set_tenant_context", lambda *args: None)
    with pytest.raises(FeatureLimitExceeded):
        consume_feature_limit(db, "clinic", "patient_document_bytes", 100, period_start=date(2026, 1, 1))
    assert "usage_count + EXCLUDED.usage_count <= :limit_value" in db.statements[1][0]
