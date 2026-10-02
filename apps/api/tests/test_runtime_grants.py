"""Static guard: every table a migration creates must be granted to healthcare_runtime by some migration.

The app connects as that role and the migrations are the only place its privileges are defined, so a table
without a GRANT fails at runtime with "permission denied" while login and health checks still pass.
"""
import re
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"
NOT_RUNTIME_TABLES: set[str] = set()  # add a table here only with a written reason


def _upgrade_body(source: str) -> str:
    return source.split("def downgrade", 1)[0]


def test_every_created_table_is_granted_to_the_runtime_role() -> None:
    created: set[str] = set()
    dropped: set[str] = set()
    granted: set[str] = set()
    for path in sorted(VERSIONS.glob("*.py")):
        body = _upgrade_body(path.read_text())
        created |= set(re.findall(r"CREATE TABLE (?:IF NOT EXISTS )?([a-z_0-9]+)", body))
        dropped |= set(re.findall(r"DROP TABLE (?:IF EXISTS )?([a-z_0-9]+)", body))
        for match in re.finditer(r"GRANT\s+[A-Z, ]+?\s+ON\s+(?:TABLE\s+)?(.*?)\s+TO\s+healthcare_runtime", body, re.S):
            granted |= {name.strip('"') for name in re.split(r"[,\s]+", match.group(1)) if name}
    missing = sorted(created - dropped - granted - NOT_RUNTIME_TABLES)
    assert not missing, f"tables with no GRANT to healthcare_runtime: {missing}"
