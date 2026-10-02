"""Static guard: a write route that never commits silently loses its changes (get_db only closes the session).

Routes that delegate to a helper which commits are listed explicitly so a new route cannot slip through unnoticed.
"""
import re
from pathlib import Path

MODULES = Path(__file__).resolve().parents[1] / "app" / "modules"
DELEGATES_AND_COMMITS = {"appointment_approve", "appointment_cancel", "appointment_reject", "public_slug_lead", "public_hostname_lead"}


def test_every_write_route_commits_or_delegates() -> None:
    missing: list[str] = []
    for path in sorted(MODULES.glob("*/*routes.py")):
        for block in re.split(r"\n(?=@\w+\.(?:get|post|patch|put|delete)\()", path.read_text()):
            match = re.match(r"@\w+\.(get|post|patch|put|delete)\(", block)
            if not match or match.group(1) == "get":
                continue
            name = re.search(r"def (\w+)", block).group(1)
            if "commit(" not in block and name not in DELEGATES_AND_COMMITS:
                missing.append(f"{path.parent.name}.{name}")
    assert not missing, f"write routes with no commit: {missing}"
