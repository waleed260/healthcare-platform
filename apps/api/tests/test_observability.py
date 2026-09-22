import json
import logging

from app.core.observability import JsonLogFormatter, RequestMetrics, redact_sentry_event


def test_metrics_are_bounded_and_report_percentiles_without_url_values():
    metrics = RequestMetrics(sample_limit=3)
    metrics.observe("GET", "/api/v1/patients/{patient_id}", 200, 10)
    metrics.observe("GET", "/api/v1/patients/{patient_id}", 200, 20)
    metrics.observe("GET", "/api/v1/patients/{patient_id}", 500, 30)
    snapshot = metrics.snapshot()
    assert snapshot["latency"][0]["p50_ms"] == 20
    assert snapshot["latency"][0]["p95_ms"] == 30
    assert all("patient_id" not in str(item) or "{patient_id}" in str(item) for item in snapshot["latency"])


def test_structured_log_formatter_keeps_only_safe_request_fields():
    record = logging.LogRecord("healthcare.request", logging.INFO, __file__, 1, "request.complete", (), None)
    record.request_id = "synthetic-request-id"
    record.route = "/api/v1/patients/{patient_id}"
    record.status_code = 200
    record.body = "must-not-be-logged"
    payload = json.loads(JsonLogFormatter().format(record))
    assert payload["request_id"] == "synthetic-request-id"
    assert "body" not in payload
    assert "patient_id" in payload["route"]


def test_sentry_redaction_removes_request_and_credential_material():
    event = {
        "request": {
            "data": {"new_password": "secret"},
            "headers": {"Authorization": "Bearer secret"},
            "cookies": {"session": "secret"},
            "query_string": "token=secret",
            "url": "https://example.test/api/v1/patients/synthetic",
        },
        "user": {"id": "synthetic-user"},
        "breadcrumbs": [{"message": "patient detail"}],
        "extra": {"body": "secret", "token": "secret", "safe": "kept"},
    }
    redacted = redact_sentry_event(event, {})
    assert redacted is not None
    assert set(redacted["request"]) == {"url"}
    assert "user" not in redacted
    assert "breadcrumbs" not in redacted
    assert redacted["extra"] == {"safe": "kept"}
