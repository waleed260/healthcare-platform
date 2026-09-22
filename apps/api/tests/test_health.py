from app.api.v1.routes import health
from app.main import app, health_live, health_ready


def test_health_endpoint() -> None:
    assert health_live() == {"status": "ok"}


def test_versioned_health_endpoint() -> None:
    assert health() == {"status": "ok", "service": "Healthcare Platform API"}


def test_ready_endpoint(monkeypatch) -> None:
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, statement):
            assert str(statement) == "SELECT 1"

    import app.main as main

    monkeypatch.setattr(main.engine, "connect", lambda: Connection())
    monkeypatch.setattr(main, "check_storage_readiness", lambda: True)
    assert health_ready() == {"status": "ready"}


def test_ready_endpoint_fails_closed_when_storage_is_unavailable(monkeypatch) -> None:
    import pytest
    from fastapi import HTTPException
    import app.main as main

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, statement):
            return None

    monkeypatch.setattr(main.engine, "connect", lambda: Connection())
    monkeypatch.setattr(main, "check_storage_readiness", lambda: False)
    with pytest.raises(HTTPException) as error:
        health_ready()
    assert error.value.status_code == 503
    assert error.value.detail == {"status": "not_ready"}


def test_cors_allows_browser_export_download_header() -> None:
    cors = next(m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware")
    assert "X-Export-Access-Token" in cors.kwargs["allow_headers"]
    assert "X-Document-Access-Token" in cors.kwargs["allow_headers"]
    assert "X-Document-Expires" in cors.kwargs["allow_headers"]
    assert "X-Original-Filename" in cors.kwargs["allow_headers"]
    assert "X-Alt-Text" in cors.kwargs["allow_headers"]
    assert "X-Preview-Token" in cors.kwargs["allow_headers"]
