from infra.release_gate import BOOLEAN_GATES, NUMERIC_LIMITS, validate_manifest


def complete_manifest() -> dict:
    return {**{key: True for key in BOOLEAN_GATES}, "metrics": dict(NUMERIC_LIMITS)}


def test_release_gate_requires_explicit_complete_evidence() -> None:
    assert validate_manifest(complete_manifest()) == []


def test_release_gate_rejects_missing_gate_and_numeric_regression() -> None:
    manifest = complete_manifest()
    manifest["backup_restore"] = False
    manifest["metrics"]["booking_p95_ms"] = 1500.1
    failures = validate_manifest(manifest)
    assert "backup_restore must be explicitly true" in failures
    assert "metrics.booking_p95_ms=1500.1 exceeds 1500.0" in failures


def test_release_gate_rejects_missing_metrics() -> None:
    manifest = complete_manifest()
    del manifest["metrics"]["rto_hours"]
    assert "metrics.rto_hours must be numeric" in validate_manifest(manifest)


def test_release_gate_rejects_non_finite_and_negative_metrics() -> None:
    manifest = complete_manifest()
    manifest["metrics"]["api_list_p95_ms"] = float("nan")
    manifest["metrics"]["rto_hours"] = -1
    failures = validate_manifest(manifest)
    assert "metrics.api_list_p95_ms must be a finite non-negative number" in failures
    assert "metrics.rto_hours must be a finite non-negative number" in failures
