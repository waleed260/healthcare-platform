"""Static guard: ON CONFLICT against a *partial* unique index must repeat the index predicate.

Postgres rejects the statement otherwise ("no unique or exclusion constraint matching the ON CONFLICT
specification"), which only shows up against a real database.
"""
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
PARTIAL_INDEX_TARGETS = ("(clinic_id, intake_key)", "(clinic_id, user_id, source_job_key)")


def test_partial_index_conflict_targets_repeat_the_predicate() -> None:
    offenders: list[str] = []
    for path in APP.rglob("*.py"):
        for match in re.finditer(r"ON CONFLICT\s*(\([^)]*\))(\s*WHERE)?", path.read_text()):
            if match.group(1) in PARTIAL_INDEX_TARGETS and not match.group(2):
                offenders.append(f"{path.relative_to(APP)}: ON CONFLICT {match.group(1)}")
    assert not offenders, offenders
