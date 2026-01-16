#!/usr/bin/env python3
"""
Fixture Validator - validates JSON fixtures against shape specifications.

Usage:
    python tools/validate_fixtures.py                    # Validate all fixtures
    python tools/validate_fixtures.py path/to/file.json # Validate specific file
    python tools/validate_fixtures.py --strict          # Fail on unknown keys
    python tools/validate_fixtures.py --jsonschema      # Use jsonschema if available

Exit codes:
    0 - All fixtures valid
    1 - Validation errors found
    2 - Configuration/file errors
"""

import json
import re
import sys
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path(__file__).parent.parent
SPECS_SHAPE_DIR = WORKSPACE_ROOT / "specs" / "shape"
FIXTURES_DIR = WORKSPACE_ROOT / "specs" / "fixtures"
SCENARIOS_DIR = WORKSPACE_ROOT / "conformance" / "scenarios"

ISO8601_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$"
)
EVENT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9\-_]+$")


class ValidationError:
    def __init__(self, path: str, message: str, severity: str = "error"):
        self.path = path
        self.message = message
        self.severity = severity

    def __str__(self):
        return f"[{self.severity.upper()}] {self.path}: {self.message}"


class ShapeValidator:
    def __init__(self, shape_spec: dict, strict: bool = False):
        self.spec = shape_spec
        self.strict = strict or shape_spec.get("strict_mode", False)
        self.errors: list[ValidationError] = []

    def validate(self, data: dict, path: str = "") -> list[ValidationError]:
        self.errors = []
        self._validate_object(data, path)
        return self.errors

    def _add_error(self, path: str, message: str, severity: str = "error"):
        self.errors.append(ValidationError(path, message, severity))

    def _validate_object(self, data: dict, path: str):
        if not isinstance(data, dict):
            self._add_error(path, f"Expected object, got {type(data).__name__}")
            return

        required = set(self.spec.get("required_fields", []))
        optional = set(self.spec.get("optional_fields", []))
        allowed = required | optional

        for field in required:
            if field not in data:
                self._add_error(f"{path}.{field}" if path else field, "Required field missing")

        if self.strict:
            for field in data:
                if field not in allowed:
                    self._add_error(
                        f"{path}.{field}" if path else field,
                        f"Unknown field (strict mode)",
                        "warning"
                    )

        for field, allowed_values in self.spec.get("enums", {}).items():
            value = self._get_nested(data, field)
            if value is not None and value not in allowed_values:
                self._add_error(
                    f"{path}.{field}" if path else field,
                    f"Invalid enum value '{value}', expected one of: {allowed_values}"
                )

        for field in self.spec.get("timestamp_fields", []):
            value = data.get(field)
            if value is not None:
                if not isinstance(value, str) or not ISO8601_PATTERN.match(value):
                    self._add_error(
                        f"{path}.{field}" if path else field,
                        f"Invalid timestamp format: '{value}'"
                    )

        for field, ref_pattern in self.spec.get("reference_fields", {}).items():
            value = data.get(field)
            if value is not None:
                if not isinstance(value, str) or not EVENT_ID_PATTERN.match(value):
                    self._add_error(
                        f"{path}.{field}" if path else field,
                        f"Invalid reference ID format: '{value}'"
                    )

        for field, nested_spec in self.spec.get("nested_shapes", {}).items():
            if field in data and data[field] is not None:
                nested_validator = ShapeValidator(nested_spec, self.strict)
                nested_path = f"{path}.{field}" if path else field
                nested_errors = nested_validator.validate(data[field], nested_path)
                self.errors.extend(nested_errors)

    def _get_nested(self, data: dict, field_path: str) -> Any:
        parts = field_path.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current


def load_shape_specs() -> dict[str, dict]:
    specs = {}
    if not SPECS_SHAPE_DIR.exists():
        return specs
    for shape_file in SPECS_SHAPE_DIR.glob("*.shape.json"):
        try:
            with open(shape_file) as f:
                spec = json.load(f)
                name = spec.get("name", shape_file.stem.replace(".shape", ""))
                specs[name] = spec
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load shape spec {shape_file}: {e}", file=sys.stderr)
    return specs


def infer_shape_type(data: dict) -> str | None:
    event_type = data.get("type")
    if event_type == "override":
        return "override-instance"
    elif event_type == "treatment":
        return "treatment-instance"
    elif event_type == "glucose":
        return "glucose-instance"
    return None


def find_fixture_files() -> list[Path]:
    fixtures = []
    if FIXTURES_DIR.exists():
        fixtures.extend(FIXTURES_DIR.glob("**/*.json"))
    if SCENARIOS_DIR.exists():
        for scenario_dir in SCENARIOS_DIR.iterdir():
            if scenario_dir.is_dir():
                fixtures.extend(scenario_dir.glob("*.json"))
    return fixtures


def validate_fixture(filepath: Path, specs: dict[str, dict], strict: bool = False) -> list[ValidationError]:
    errors = []
    try:
        with open(filepath) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return [ValidationError(str(filepath), f"Invalid JSON: {e}")]
    except IOError as e:
        return [ValidationError(str(filepath), f"Could not read file: {e}")]

    items = data if isinstance(data, list) else [data]

    for i, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(ValidationError(
                f"{filepath}[{i}]" if len(items) > 1 else str(filepath),
                f"Expected object, got {type(item).__name__}"
            ))
            continue

        shape_type = infer_shape_type(item)
        if shape_type and shape_type in specs:
            validator = ShapeValidator(specs[shape_type], strict)
            path = f"{filepath}[{i}]" if len(items) > 1 else str(filepath)
            item_errors = validator.validate(item, path)
            errors.extend(item_errors)
        elif shape_type:
            errors.append(ValidationError(
                str(filepath),
                f"No shape spec found for type '{shape_type}'",
                "warning"
            ))

    return errors


def try_jsonschema_validation(filepath: Path, schema_path: Path) -> list[ValidationError]:
    try:
        import jsonschema
    except ImportError:
        return []

    errors = []
    try:
        with open(filepath) as f:
            data = json.load(f)
        with open(schema_path) as f:
            schema = json.load(f)

        items = data if isinstance(data, list) else [data]
        for i, item in enumerate(items):
            try:
                jsonschema.validate(item, schema)
            except jsonschema.ValidationError as e:
                path = f"{filepath}[{i}]" if len(items) > 1 else str(filepath)
                errors.append(ValidationError(path, f"JSON Schema: {e.message}"))
    except Exception as e:
        errors.append(ValidationError(str(filepath), f"JSON Schema validation failed: {e}"))

    return errors


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Validate fixtures against shape specifications")
    parser.add_argument("files", nargs="*", help="Specific files to validate (default: all fixtures)")
    parser.add_argument("--strict", action="store_true", help="Fail on unknown keys")
    parser.add_argument("--jsonschema", action="store_true", help="Also run jsonschema validation if available")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    specs = load_shape_specs()
    if not specs:
        print("Warning: No shape specifications found in specs/shape/", file=sys.stderr)

    if args.files:
        files = [Path(f) for f in args.files]
    else:
        files = find_fixture_files()

    if not files:
        print("No fixture files found to validate.")
        return 0

    all_errors = []
    validated_count = 0

    for filepath in files:
        if args.verbose:
            print(f"Validating {filepath}...")

        errors = validate_fixture(filepath, specs, args.strict)
        all_errors.extend(errors)

        if args.jsonschema:
            schema_path = WORKSPACE_ROOT / "specs" / "jsonschema" / "aid-events.schema.json"
            if schema_path.exists():
                jsonschema_errors = try_jsonschema_validation(filepath, schema_path)
                all_errors.extend(jsonschema_errors)

        validated_count += 1

    error_count = sum(1 for e in all_errors if e.severity == "error")
    warning_count = sum(1 for e in all_errors if e.severity == "warning")

    for error in all_errors:
        print(error)

    print()
    print(f"Validated {validated_count} file(s): {error_count} error(s), {warning_count} warning(s)")

    return 1 if error_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
