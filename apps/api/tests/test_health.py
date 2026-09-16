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
    assert health_ready() == {"status": "ready"}


def test_cors_allows_browser_export_download_header() -> None:
    cors = next(m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware")
    assert "X-Export-Access-Token" in cors.kwargs["allow_headers"]
