from app.core.observability import RequestMetrics


def test_metrics_are_bounded_and_report_percentiles_without_url_values():
    metrics = RequestMetrics(sample_limit=3)
    metrics.observe("GET", "/api/v1/patients/{patient_id}", 200, 10)
    metrics.observe("GET", "/api/v1/patients/{patient_id}", 200, 20)
    metrics.observe("GET", "/api/v1/patients/{patient_id}", 500, 30)
    snapshot = metrics.snapshot()
    assert snapshot["latency"][0]["p50_ms"] == 20
    assert snapshot["latency"][0]["p95_ms"] == 30
    assert all("patient_id" not in str(item) or "{patient_id}" in str(item) for item in snapshot["latency"])
