import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from infra.release_gate import BOOLEAN_GATES, NUMERIC_LIMITS, validate_manifest


def _passing_manifest() -> dict:
    return {
        **{gate: True for gate in BOOLEAN_GATES},
        "metrics": {metric: maximum for metric, maximum in NUMERIC_LIMITS.items()},
    }


def test_release_gate_accepts_only_complete_bounded_evidence() -> None:
    assert validate_manifest(_passing_manifest()) == []


def test_release_gate_fails_closed_for_missing_boolean_and_metrics() -> None:
    failures = validate_manifest({})

    assert "synthetic_data_only must be explicitly true" in failures
    assert "metrics must be a JSON object" in failures


def test_release_gate_rejects_non_finite_or_over_target_metrics() -> None:
    manifest = _passing_manifest()
    manifest["metrics"]["api_list_p95_ms"] = 500.1
    manifest["metrics"]["rto_hours"] = float("nan")

    failures = validate_manifest(manifest)

    assert "metrics.api_list_p95_ms=500.1 exceeds 500.0" in failures
    assert "metrics.rto_hours must be a finite non-negative number" in failures
