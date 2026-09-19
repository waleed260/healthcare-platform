from unittest.mock import Mock
from uuid import uuid4

from app.core.config import get_settings
from app.core.security import generate_field_key
from app.modules.files import jobs


def test_legacy_document_metadata_job_encrypts_and_replaces_plaintext(monkeypatch) -> None:
    clinic_id, document_id, job_id = uuid4(), uuid4(), uuid4()
    monkeypatch.setenv("FIELD_ENCRYPTION_KEYS", generate_field_key())
    get_settings.cache_clear()
    job = {"id": job_id, "attempts": 1, "job_key": f"document-metadata-encrypt:{document_id}"}
    row = {"original_filename": "synthetic-private.pdf", "original_filename_ciphertext": None, "mime_type": "application/pdf"}
    db = Mock()
    select = Mock()
    select.mappings.return_value.one_or_none.return_value = row
    db.execute.return_value = select
    monkeypatch.setattr(jobs, "claim_next_job", lambda *_args, **_kwargs: job)
    complete = Mock()
    monkeypatch.setattr(jobs, "complete_job", complete)

    try:
        assert jobs.run_next_document_metadata_encryption(db, clinic_id) == "encrypted"
    finally:
        get_settings.cache_clear()

    update_calls = [call for call in db.execute.call_args_list if "UPDATE patient_documents" in str(call.args[0])]
    assert len(update_calls) == 1
    parameters = update_calls[0].args[1]
    assert parameters["legacy_filename"] == "document.pdf"
    assert parameters["ciphertext"] != "synthetic-private.pdf"
    complete.assert_called_once_with(db, clinic_id, job_id)
    assert db.commit.called
