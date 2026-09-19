from uuid import uuid4
from unittest.mock import Mock, patch

from app.modules.governance.jobs import run_expired_artifact_cleanup
from app.worker import build_parser


def test_worker_parser_requires_explicit_clinic_and_supports_safe_defaults():
    clinic_id = uuid4()
    args = build_parser().parse_args(["--clinic-id", str(clinic_id), "--once"])
    assert args.clinic_id == clinic_id
    assert args.job_type == "document_scan"
    assert args.once is True


def test_worker_parser_rejects_unknown_job_type():
    try:
        build_parser().parse_args(["--clinic-id", str(uuid4()), "--job-type", "all"])
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("unknown job type should be rejected")


def test_worker_parser_supports_tenant_scoped_retention_cleanup():
    args = build_parser().parse_args(["--clinic-id", str(uuid4()), "--job-type", "retention_cleanup", "--once"])
    assert args.job_type == "retention_cleanup"


def test_worker_parser_supports_tenant_scoped_metadata_encryption():
    args = build_parser().parse_args(["--clinic-id", str(uuid4()), "--job-type", "document_metadata_encrypt", "--once"])
    assert args.job_type == "document_metadata_encrypt"


def test_expired_artifact_cleanup_deletes_objects_and_keeps_metadata():
    clinic_id = uuid4()
    export_id = uuid4()
    select_result = Mock()
    select_result.mappings.return_value.all.return_value = [{"id": export_id, "storage_key": "exports/x.json"}]
    preview_result = Mock(rowcount=2)
    db = Mock()

    def execute(statement, _params):
        sql = str(statement)
        if "SELECT id, storage_key" in sql:
            return select_result
        if "DELETE FROM website_preview_tokens" in sql:
            return preview_result
        return Mock()

    db.execute.side_effect = execute
    with patch("app.modules.governance.jobs.delete_private_object") as delete_object:
        result = run_expired_artifact_cleanup(db, clinic_id)

    delete_object.assert_called_once_with("exports/x.json")
    assert result == {"exports_expired": 1, "preview_tokens_deleted": 2}
    assert db.commit.called
