"""Dry-run reconciliation for patient merges performed before the merge fix.

The old merge route repointed only a few tables, so any merge executed on that
code left the source patient's documents, media, invoices, packages, clinical
forms/tools, prescriptions and converted-lead pointer stranded on the archived
source row. Fixing the code does not heal rows already orphaned. This job scans
the authoritative ``patient_merge_events`` log and, for every source patient,
counts rows that still point at it across the full merge registry.

It is strictly READ-ONLY: it reports, it never repairs. Clinical and financial
conflicts must be resolved by a human against a backup — do not automate that.

Usage:
    PYTHONPATH=. python scripts/reconcile_merges.py [--database-url URL] [--json] [--fail-on-findings]

The database URL defaults to RECONCILE_DATABASE_URL / DATABASE_MIGRATION_URL /
DATABASE_URL; use the owner/migration role so the scan sees every clinic.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field

import psycopg
from psycopg.rows import dict_row

from app.modules.crm.merge import _DEDUPE_MEMBERSHIP, _DIRECT_REPOINT

# Every relationship a complete merge moves off the source patient. Table and
# column names come from this trusted internal registry, never user input, so
# interpolating them into the count query is safe.
_PATIENT_ID_TABLES = list(_DIRECT_REPOINT) + [table for table, _, _ in _DEDUPE_MEMBERSHIP] + ["clinical_tool_states"]
_CHECKS: list[tuple[str, str]] = [(table, "patient_id") for table in _PATIENT_ID_TABLES] + [("leads", "converted_to_patient_id")]


@dataclass
class MergeFinding:
    clinic_id: str
    source_patient_id: str
    target_patient_id: str
    not_tombstoned: bool = False
    orphans: dict[str, int] = field(default_factory=dict)

    @property
    def is_clean(self) -> bool:
        return not self.not_tombstoned and not self.orphans

    def as_dict(self) -> dict:
        return {
            "clinic_id": self.clinic_id,
            "source_patient_id": self.source_patient_id,
            "target_patient_id": self.target_patient_id,
            "not_tombstoned": self.not_tombstoned,
            "orphans": self.orphans,
        }


def reconcile(conn: psycopg.Connection) -> list[MergeFinding]:
    """Return a finding per merge event that still has orphaned rows or whose
    source patient was never tombstoned. An empty list means every recorded
    merge is fully consistent."""
    findings: list[MergeFinding] = []
    with conn.cursor(row_factory=dict_row) as cur:
        events = cur.execute(
            "SELECT clinic_id, source_patient_id, target_patient_id FROM patient_merge_events ORDER BY created_at"
        ).fetchall()
    for event in events:
        clinic_id, source_id, target_id = event["clinic_id"], event["source_patient_id"], event["target_patient_id"]
        finding = MergeFinding(clinic_id=str(clinic_id), source_patient_id=str(source_id), target_patient_id=str(target_id))
        with conn.cursor(row_factory=dict_row) as cur:
            patient = cur.execute(
                "SELECT status, duplicate_of FROM patients WHERE clinic_id = %s AND id = %s",
                (clinic_id, source_id),
            ).fetchone()
            if patient is not None and not (patient["status"] == "merged" and patient["duplicate_of"] == target_id):
                finding.not_tombstoned = True
            for table, column in _CHECKS:
                count = cur.execute(
                    f"SELECT count(*) AS n FROM {table} WHERE clinic_id = %s AND {column} = %s",
                    (clinic_id, source_id),
                ).fetchone()["n"]
                if count:
                    finding.orphans[f"{table}.{column}"] = count
        if not finding.is_clean:
            findings.append(finding)
    return findings


def _connection_url(override: str | None) -> str:
    value = override or os.environ.get("RECONCILE_DATABASE_URL") or os.environ.get("DATABASE_MIGRATION_URL") or os.environ.get("DATABASE_URL")
    if not value:
        raise SystemExit("RECONCILE_DATABASE_URL or DATABASE_URL is required")
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run reconciliation of patient merges (read-only).")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--fail-on-findings", action="store_true", help="exit non-zero if any merge is inconsistent")
    args = parser.parse_args()

    with psycopg.connect(_connection_url(args.database_url)) as conn:
        findings = reconcile(conn)

    if args.json:
        print(json.dumps([finding.as_dict() for finding in findings], indent=2, sort_keys=True))
    elif not findings:
        print("All recorded patient merges are consistent: no orphaned rows and every source is tombstoned.")
    else:
        print(f"Found {len(findings)} merge(s) needing attention (READ-ONLY — nothing was changed):\n")
        for finding in findings:
            print(f"- clinic {finding.clinic_id}  source {finding.source_patient_id} -> target {finding.target_patient_id}")
            if finding.not_tombstoned:
                print("    source patient is NOT tombstoned (status/duplicate_of not set to the target)")
            for relationship, count in sorted(finding.orphans.items()):
                print(f"    {count} orphaned row(s) in {relationship} (still point at the source)")
        print("\nBack up first. Resolve clinical/financial conflicts by hand; do not auto-repair.")

    return 1 if (args.fail_on_findings and findings) else 0


if __name__ == "__main__":
    sys.exit(main())
