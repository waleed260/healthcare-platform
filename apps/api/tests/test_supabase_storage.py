from types import SimpleNamespace

from app.core.config import get_settings
from app.modules.files import storage


def test_supabase_private_storage_uses_server_only_headers_and_encoded_key(monkeypatch):
    settings = SimpleNamespace(
        storage_backend="supabase",
        supabase_url="https://project.supabase.co",
        supabase_service_role_key="server-only-test-key",
        supabase_private_bucket="private-healthcare",
        supabase_public_bucket="public-healthcare",
    )
    monkeypatch.setattr(storage, "get_settings", lambda: settings)
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return b"stored"

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["method"] = request.method
        captured["body"] = request.data
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(storage, "urlopen", fake_urlopen)
    storage.put_private_object("clinic/a patient/document.pdf", b"payload")
    assert captured["method"] == "POST"
    assert "a%20patient" in captured["url"]
    assert captured["body"] == b"payload"
    assert captured["headers"]["Authorization"] == "Bearer server-only-test-key"
    assert captured["headers"]["X-upsert"] == "false"


def test_local_storage_remains_default(monkeypatch, tmp_path):
    monkeypatch.setenv("PRIVATE_STORAGE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    try:
        assert get_settings().storage_backend == "local"
    finally:
        get_settings.cache_clear()
