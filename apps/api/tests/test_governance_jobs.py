from uuid import uuid4

from app.modules.governance import jobs


class _DB:
    def __init__(self) -> None:
        self.statements: list[object] = []
        self.commits = 0

    def execute(self, statement, params=None):
        self.statements.append((statement, params))
        return object()

    def commit(self) -> None:
        self.commits += 1


def test_export_worker_records_completion_with_export_context(monkeypatch) -> None:
    clinic_id = uuid4()
    export_id = uuid4()
    job_id = uuid4()
    requested_by = uuid4()
    db = _DB()
    events: list[dict] = []

    monkeypatch.setattr(jobs, "claim_next_job", lambda *args, **kwargs: {
        "id": job_id,
        "job_key": f"export:{export_id}",
        "attempts": 1,
    })
    monkeypatch.setattr(jobs, "set_tenant_context", lambda *args, **kwargs: None)
    monkeypatch.setattr(jobs, "_build_export", lambda *args, **kwargs: (
        {"export_type": "patient_access", "patient": {"synthetic": True}},
        {"requested_by_user_id": requested_by, "export_type": "patient_access"},
    ))
    monkeypatch.setattr(jobs, "put_private_object", lambda *args, **kwargs: None)
    monkeypatch.setattr(jobs, "record_event", lambda _db, **kwargs: events.append(kwargs))
    monkeypatch.setattr(jobs, "complete_job", lambda *args, **kwargs: None)

    assert jobs.run_next_export_job(db, clinic_id) == "completed"
    assert events == [{
        "clinic_id": clinic_id,
        "actor_user_id": requested_by,
        "action": "export.complete",
        "entity_type": "export_job",
        "entity_id": export_id,
        "outcome": "success",
        "metadata": {"export_type": "patient_access"},
    }]
    assert db.commits == 1
