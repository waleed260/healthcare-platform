#!/usr/bin/env python3
"""Validate the evidence manifest required by the Healthcare Platform launch gate."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

BOOLEAN_GATES = (
    "synthetic_data_only", "cross_tenant_isolation", "forced_rls",
    "appointment_concurrency", "auth_mfa_recovery", "csrf_cors_csp_rate_limits",
    "private_files", "website_publishing", "backup_restore", "wcag_aa",
    "plans_limits", "audit_support_expiry", "secrets_scan", "retention_approval",
    "monitoring_runbooks", "pilot_owner_approval",
)
NUMERIC_LIMITS = {
    "api_list_p95_ms": 500.0, "availability_p95_ms": 800.0,
    "booking_p95_ms": 1500.0, "dashboard_p75_ms": 2500.0,
    "public_lcp_p75_ms": 2500.0, "public_inp_p75_ms": 200.0,
    "public_cls_p75": 0.1, "rpo_hours": 24.0, "rto_hours": 8.0,
}


def validate_manifest(manifest: Any) -> list[str]:
    """Return actionable failures; an empty list means the manifest passes."""
    if not isinstance(manifest, dict):
        return ["manifest must be a JSON object"]
    failures: list[str] = []
    for key in BOOLEAN_GATES:
        if manifest.get(key) is not True:
            failures.append(f"{key} must be explicitly true")
    metrics = manifest.get("metrics")
    if not isinstance(metrics, dict):
        return [*failures, "metrics must be a JSON object"]
    for key, maximum in NUMERIC_LIMITS.items():
        value = metrics.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            failures.append(f"metrics.{key} must be numeric")
        elif not math.isfinite(value) or value < 0:
            failures.append(f"metrics.{key} must be a finite non-negative number")
        elif value > maximum:
            failures.append(f"metrics.{key}={value} exceeds {maximum}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path, help="JSON launch-evidence manifest")
    args = parser.parse_args()
    try:
        manifest = json.loads(args.evidence.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"release gate input error: {exc}", file=sys.stderr)
        return 2
    failures = validate_manifest(manifest)
    if failures:
        print("RELEASE GATE: FAILED")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print("RELEASE GATE: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
