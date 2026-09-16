"""Export the FastAPI schema used as the committed frontend/API contract.

Run from the repository root with ``PYTHONPATH=apps/api python apps/api/scripts/export_openapi.py``.
The application is imported only to construct its in-process OpenAPI document;
the exporter does not connect to the database.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.main import app


ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / "packages" / "contracts" / "openapi.json"


def main() -> None:
    OUTPUT.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT} ({len(app.routes)} routes)")


if __name__ == "__main__":
    main()
