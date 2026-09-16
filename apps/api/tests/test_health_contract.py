from app.api.v1.routes import health


def test_versioned_health_does_not_disclose_environment() -> None:
    assert health() == {"status": "ok", "service": "Healthcare Platform API"}
