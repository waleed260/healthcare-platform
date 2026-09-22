from pathlib import Path
from stat import S_IMODE

from app.core.config import get_settings
from app.modules.files import storage
from app.modules.files.storage import check_storage_readiness


def test_local_storage_readiness_checks_both_roots(monkeypatch, tmp_path: Path) -> None:
    private_root = tmp_path / "private"
    public_root = tmp_path / "public"
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("PRIVATE_STORAGE_ROOT", str(private_root))
    monkeypatch.setenv("PUBLIC_STORAGE_ROOT", str(public_root))
    get_settings.cache_clear()
    try:
        assert check_storage_readiness() is True
        assert private_root.is_dir()
        assert public_root.is_dir()
        assert S_IMODE(private_root.stat().st_mode) & 0o077 == 0
        assert S_IMODE(public_root.stat().st_mode) & 0o002 == 0
    finally:
        get_settings.cache_clear()


def test_supabase_storage_readiness_checks_both_buckets_with_bounded_timeout(monkeypatch) -> None:
    calls: list[tuple[str, float, str]] = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, timeout, request.headers["Authorization"]))
        return Response()

    monkeypatch.setenv("STORAGE_BACKEND", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://storage.example.test")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "synthetic-service-role")
    monkeypatch.setenv("SUPABASE_PRIVATE_BUCKET", "private-healthcare")
    monkeypatch.setenv("SUPABASE_PUBLIC_BUCKET", "public-healthcare")
    monkeypatch.setattr(storage, "urlopen", fake_urlopen)
    get_settings.cache_clear()
    try:
        assert check_storage_readiness() is True
        assert [url for url, _, _ in calls] == [
            "https://storage.example.test/storage/v1/bucket/private-healthcare",
            "https://storage.example.test/storage/v1/bucket/public-healthcare",
        ]
        assert all(timeout == 2 for _, timeout, _ in calls)
        assert all("synthetic-service-role" not in url for url, _, _ in calls)
    finally:
        get_settings.cache_clear()
