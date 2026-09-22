#!/usr/bin/env python3
"""Generate the shared TypeScript literal types from the committed OpenAPI file."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OPENAPI = ROOT / "openapi.json"
OUTPUT = ROOT / "openapi-types.ts"


def type_name(schema_name: str, property_name: str) -> str:
    words = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|[0-9]+", f"{schema_name}_{property_name}")
    return "".join(word[:1].upper() + word[1:] for word in words) + "Value"


def main() -> None:
    document = json.loads(OPENAPI.read_text(encoding="utf-8"))
    aliases: dict[str, tuple[str, ...]] = {}
    for schema_name, schema in sorted(document.get("components", {}).get("schemas", {}).items()):
        for property_name, property_schema in sorted(schema.get("properties", {}).items()):
            match = re.fullmatch(r"\^\(([^)]+)\)\$", property_schema.get("pattern", ""))
            if not match:
                continue
            values = tuple(match.group(1).split("|"))
            if all(re.fullmatch(r"[a-z][a-z0-9_]*", value) for value in values):
                aliases[type_name(schema_name, property_name)] = values

    lines = [
        "// GENERATED FILE. Do not edit; run: python3 packages/contracts/generate_types.py",
        "",
    ]
    for name, values in sorted(aliases.items()):
        lines.append(f"export type {name} = " + " | ".join(json.dumps(value) for value in values) + ";")
    lines.append("")
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
