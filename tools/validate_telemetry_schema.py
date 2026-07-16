#!/usr/bin/env python3
"""Validate Nightscout telemetry schema fixtures.

Valid fixtures under specs/fixtures/telemetry/valid must pass.
Invalid fixtures under specs/fixtures/telemetry/invalid must fail.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError as exc:  # pragma: no cover - environment guard
    print(f"jsonschema is required: {exc}", file=sys.stderr)
    raise SystemExit(2)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "specs" / "jsonschema" / "nightscout-telemetry-aggregate.schema.json"
FIXTURE_ROOT = ROOT / "specs" / "fixtures" / "telemetry"


def load_json(path: Path) -> object:
    with path.open() as f:
        return json.load(f)


def main() -> int:
    schema = load_json(SCHEMA_PATH)
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)

    errors: list[str] = []

    for path in sorted((FIXTURE_ROOT / "valid").glob("*.json")):
        payload = load_json(path)
        messages = sorted(error.message for error in validator.iter_errors(payload))
        if messages:
            errors.append(f"{path}: expected valid, got {messages}")

    for path in sorted((FIXTURE_ROOT / "invalid").glob("*.json")):
        payload = load_json(path)
        messages = sorted(error.message for error in validator.iter_errors(payload))
        if not messages:
            errors.append(f"{path}: expected invalid, got valid")

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    valid_count = len(list((FIXTURE_ROOT / "valid").glob("*.json")))
    invalid_count = len(list((FIXTURE_ROOT / "invalid").glob("*.json")))
    print(f"Telemetry schema fixtures ok: {valid_count} valid, {invalid_count} invalid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
