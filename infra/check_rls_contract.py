#!/usr/bin/env python3
"""Verify the mandatory tenant RLS contract in generated Alembic SQL."""

from __future__ import annotations

import re
import sys
from pathlib import Path


REQUIRED_TABLES = {
    "branches", "user_roles", "user_branch_scopes", "branch_hours", "clinic_holidays",
    "doctor_profiles", "services", "doctor_services", "branch_doctors", "branch_services",
    "rooms", "resources", "patients", "appointments", "appointment_history",
    "booking_management_tokens", "appointment_reschedule_requests", "queue_entries",
    "follow_up_tasks", "notifications", "browser_push_subscriptions", "patient_documents",
    "file_scan_events", "patient_contacts", "tags", "patient_tags", "patient_notes",
    "consent_records", "patient_merge_events", "privacy_requests", "export_jobs",
    "background_jobs", "clinic_subscriptions", "support_access_sessions", "audit_events",
    "clinic_feature_usage", "availability_rules", "leave_blocks", "blocked_slots",
    "resource_blocks", "booking_questions", "service_booking_questions", "appointment_answers",
    "websites", "website_versions", "website_pages", "website_sections", "website_media",
    "domain_verifications", "website_media_scan_events", "website_preview_tokens",
    "document_access_events", "doctor_rooms", "access_tokens", "clinic_care_policies",
    "patient_care_team", "tenant_probe_records", "staff_invitations",
}


def validate_sql(sql: str) -> list[str]:
    failures: list[str] = []
    for table in sorted(REQUIRED_TABLES):
        if f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;" not in sql:
            failures.append(f"{table}: forced RLS statement missing")
        if not re.search(rf"CREATE POLICY [^;]+ ON {re.escape(table)}\b", sql, re.DOTALL):
            failures.append(f"{table}: RLS policy missing")
    if "CONSTRAINT fk_access_tokens_user_tenant" not in sql:
        failures.append("access_tokens: same-tenant user foreign key missing")
    return failures


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} OFFLINE_SQL", file=sys.stderr)
        return 2
    try:
        sql = Path(sys.argv[1]).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"RLS contract input error: {exc}", file=sys.stderr)
        return 2
    failures = validate_sql(sql)
    if failures:
        print("RLS CONTRACT: FAILED")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print(f"RLS CONTRACT: PASSED ({len(REQUIRED_TABLES)} forced tables and policies)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
