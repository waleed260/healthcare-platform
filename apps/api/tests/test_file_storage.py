import pytest

from app.core.config import get_settings
from app.modules.files.storage import delete_private_object, put_private_object, read_private_object


def test_private_storage_rejects_traversal_and_round_trips(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PRIVATE_STORAGE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    try:
        put_private_object("clinic/patient/document.pdf", b"synthetic document")
        assert read_private_object("clinic/patient/document.pdf") == b"synthetic document"
        with pytest.raises(ValueError):
            read_private_object("../outside.pdf")
    finally:
        delete_private_object("clinic/patient/document.pdf")
        get_settings.cache_clear()
