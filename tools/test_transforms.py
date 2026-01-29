#!/usr/bin/env python3
"""
Field Transform Test Runner - validates cross-system field mappings.

Unlike test_conversions.py which tests unit conversions (mg/dL → mmol/L),
this tool tests field transformations:
  - Field renaming (sgv → glucose)
  - Nested field extraction (devicestatus.pump.iob → iob)
  - Field type coercion (number → string)
  - Required field validation
  - Cross-system field mapping

Usage:
    python tools/test_transforms.py                      # Run all tests
    python tools/test_transforms.py --source loop       # Filter by source
    python tools/test_transforms.py --target nightscout # Filter by target
    python tools/test_transforms.py -v                  # Verbose output

Exit codes:
    0 - All tests pass
    1 - Test failures
    2 - Configuration errors
"""

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

yaml: Any = None
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

WORKSPACE_ROOT = Path(__file__).parent.parent
TRANSFORMS_DIR = WORKSPACE_ROOT / "conformance" / "field-transforms"


class TransformResult:
    """Result of a single transform test."""
    
    def __init__(self, test_id: str, passed: bool,
                 field: str = "", expected: Any = None,
                 actual: Any = None, message: str = ""):
        self.test_id = test_id
        self.passed = passed
        self.field = field
        self.expected = expected
        self.actual = actual
        self.message = message

    def __str__(self) -> str:
        status = "✓ PASS" if self.passed else "✗ FAIL"
        if self.passed:
            return f"{status} {self.test_id}"
        else:
            if self.message:
                return f"{status} {self.test_id}: {self.message}"
            return f"{status} {self.test_id}: {self.field} expected {self.expected!r}, got {self.actual!r}"


def get_nested_value(obj: dict, path: str) -> Any:
    """
    Extract nested value using dot notation.
    
    Examples:
        get_nested_value({"a": {"b": 1}}, "a.b") → 1
        get_nested_value({"a": [{"x": 1}]}, "a[0].x") → 1
    """
    if not path:
        return obj
    
    current = obj
    # Handle array notation: a[0].b → ["a", "[0]", "b"]
    parts = re.split(r'\.(?![^\[]*\])', path)
    
    for part in parts:
        if current is None:
            return None
            
        # Handle array index
        array_match = re.match(r'(\w*)\[(\d+)\]', part)
        if array_match:
            key, index = array_match.groups()
            if key:
                current = current.get(key) if isinstance(current, dict) else None
            if isinstance(current, list) and int(index) < len(current):
                current = current[int(index)]
            else:
                return None
        else:
            current = current.get(part) if isinstance(current, dict) else None
    
    return current


def set_nested_value(obj: dict, path: str, value: Any) -> None:
    """Set nested value using dot notation."""
    parts = path.split('.')
    current = obj
    
    for part in parts[:-1]:
        if part not in current:
            current[part] = {}
        current = current[part]
    
    current[parts[-1]] = value


def apply_transform(input_obj: dict, transform: dict) -> dict:
    """
    Apply a single field transformation.
    
    Transform types:
        - rename: Change field name
        - extract: Extract nested field to top level
        - coerce: Convert type
        - default: Set default if missing
        - compute: Calculate from other fields
    """
    output = dict(input_obj)  # Shallow copy
    transform_type = transform.get("type", "rename")
    
    if transform_type == "rename":
        source_field = transform["from"]
        target_field = transform["to"]
        value = get_nested_value(input_obj, source_field)
        if value is not None:
            # Remove old field (only top-level)
            if '.' not in source_field and source_field in output:
                del output[source_field]
            set_nested_value(output, target_field, value)
    
    elif transform_type == "extract":
        source_path = transform["from"]
        target_field = transform["to"]
        value = get_nested_value(input_obj, source_path)
        if value is not None:
            output[target_field] = value
    
    elif transform_type == "coerce":
        field = transform["field"]
        to_type = transform["to_type"]
        value = get_nested_value(input_obj, field)
        if value is not None:
            if to_type == "string":
                output[field] = str(value)
            elif to_type == "number":
                output[field] = float(value)
            elif to_type == "integer":
                output[field] = int(value)
            elif to_type == "boolean":
                output[field] = bool(value)
    
    elif transform_type == "default":
        field = transform["field"]
        default_value = transform["value"]
        if field not in output or output[field] is None:
            output[field] = default_value
    
    elif transform_type == "compute":
        target_field = transform["to"]
        expression = transform["expression"]
        # Simple expression evaluation (safe subset)
        # Supports: field references, basic math
        try:
            result = eval_expression(expression, input_obj)
            output[target_field] = result
        except Exception:
            pass  # Skip on error
    
    return output


def eval_expression(expr: str, context: dict) -> Any:
    """
    Evaluate a simple expression in context.
    
    Supported:
        - Field references: ${fieldName}
        - Basic math: +, -, *, /
        - String concat: ${a} + ${b}
    """
    # Replace field references
    def replace_field(match):
        field_name = match.group(1)
        value = get_nested_value(context, field_name)
        if isinstance(value, str):
            return f'"{value}"'
        return str(value) if value is not None else 'None'
    
    resolved = re.sub(r'\$\{([^}]+)\}', replace_field, expr)
    
    # Safe eval with no builtins
    return eval(resolved, {"__builtins__": {}}, {})


def apply_transform_pipeline(input_obj: dict, transforms: list[dict]) -> dict:
    """Apply a sequence of transforms."""
    result = dict(input_obj)
    for transform in transforms:
        result = apply_transform(result, transform)
    return result


def validate_output(output: dict, expected: dict, strict: bool = False) -> list[tuple[str, Any, Any]]:
    """
    Validate output matches expected.
    
    Returns list of (field, expected, actual) for failures.
    """
    failures = []
    
    for field, expected_value in expected.items():
        actual_value = get_nested_value(output, field)
        
        # Type-flexible comparison
        if not values_match(expected_value, actual_value):
            failures.append((field, expected_value, actual_value))
    
    if strict:
        # Check for unexpected fields
        for field in output:
            if field not in expected:
                failures.append((field, "<absent>", output[field]))
    
    return failures


def values_match(expected: Any, actual: Any) -> bool:
    """Compare values with type flexibility."""
    if expected == actual:
        return True
    
    # String/number equivalence
    if isinstance(expected, (int, float)) and isinstance(actual, str):
        try:
            return expected == float(actual)
        except ValueError:
            return False
    
    if isinstance(expected, str) and isinstance(actual, (int, float)):
        try:
            return float(expected) == actual
        except ValueError:
            return False
    
    # Nested dict comparison
    if isinstance(expected, dict) and isinstance(actual, dict):
        return all(
            k in actual and values_match(v, actual[k])
            for k, v in expected.items()
        )
    
    return False


def run_transform_test(test: dict) -> list[TransformResult]:
    """Run a single transform test case."""
    test_id = test.get("id", "unknown")
    input_obj = test.get("input", {})
    transforms = test.get("transforms", [])
    expected = test.get("expected", {})
    strict = test.get("strict", False)
    
    results = []
    
    try:
        output = apply_transform_pipeline(input_obj, transforms)
        failures = validate_output(output, expected, strict)
        
        if not failures:
            results.append(TransformResult(test_id, passed=True))
        else:
            for field, exp, act in failures:
                results.append(TransformResult(
                    test_id=test_id,
                    passed=False,
                    field=field,
                    expected=exp,
                    actual=act
                ))
    
    except Exception as e:
        results.append(TransformResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}"
        ))
    
    return results


def load_transform_tests(filepath: Path) -> list[dict]:
    """Load transform test cases from YAML file."""
    if not filepath.exists():
        return []
    
    if not YAML_AVAILABLE:
        print(f"Warning: PyYAML not installed, cannot parse {filepath}", file=sys.stderr)
        return []
    
    try:
        with open(filepath) as f:
            data = yaml.safe_load(f)
            return data.get("tests", [])
    except Exception as e:
        print(f"Error loading {filepath}: {e}", file=sys.stderr)
        return []


def discover_test_files() -> list[Path]:
    """Find all transform test YAML files."""
    files = []
    if TRANSFORMS_DIR.exists():
        for path in TRANSFORMS_DIR.glob("*.yaml"):
            if not path.name.startswith("_"):
                files.append(path)
        for path in TRANSFORMS_DIR.glob("*.yml"):
            if not path.name.startswith("_"):
                files.append(path)
    return sorted(files)


def main():
    parser = argparse.ArgumentParser(description="Run field transform tests")
    parser.add_argument("--id", help="Filter tests by ID pattern (glob)")
    parser.add_argument("--source", help="Filter by source system")
    parser.add_argument("--target", help="Filter by target system")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show all results")
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    parser.add_argument("--list", action="store_true", help="List test IDs only")
    args = parser.parse_args()

    if not YAML_AVAILABLE:
        print("Error: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
        return 2

    test_files = discover_test_files()
    if not test_files:
        print("No transform test files found in conformance/field-transforms/")
        print("Creating sample test file...")
        create_sample_tests()
        test_files = discover_test_files()

    all_tests: list[dict] = []
    for filepath in test_files:
        tests = load_transform_tests(filepath)
        for test in tests:
            test["_source_file"] = str(filepath.name)
        all_tests.extend(tests)

    # Apply filters
    if args.id:
        all_tests = [t for t in all_tests if fnmatch.fnmatch(t.get("id", ""), args.id)]
    if args.source:
        all_tests = [t for t in all_tests 
                     if args.source.lower() in t.get("source_system", "").lower()]
    if args.target:
        all_tests = [t for t in all_tests 
                     if args.target.lower() in t.get("target_system", "").lower()]

    if not all_tests:
        print("No tests match the filter criteria")
        return 0

    if args.list:
        for test in all_tests:
            print(f"{test.get('id', 'unknown')}: {test.get('description', '')}")
        return 0

    print(f"Running {len(all_tests)} transform tests...\n")

    all_results: list[TransformResult] = []
    for test in all_tests:
        results = run_transform_test(test)
        all_results.extend(results)
        
        for result in results:
            if args.verbose or not result.passed:
                print(result)

    passed = sum(1 for r in all_results if r.passed)
    failed = len(all_results) - passed

    print(f"\n{'─' * 40}")
    print(f"Results: {passed} passed, {failed} failed")

    if args.json:
        report = {
            "total": len(all_results),
            "passed": passed,
            "failed": failed,
            "tests": [
                {
                    "id": r.test_id,
                    "passed": r.passed,
                    "field": r.field,
                    "expected": r.expected,
                    "actual": r.actual,
                    "message": r.message
                }
                for r in all_results
            ]
        }
        print(json.dumps(report, indent=2))

    return 1 if failed > 0 else 0


def create_sample_tests():
    """Create sample test file if none exists."""
    TRANSFORMS_DIR.mkdir(parents=True, exist_ok=True)
    
    sample = """# Field Transform Test Cases
# Validates cross-system field mappings in the Nightscout ecosystem

tests:

  # === Loop → Nightscout Entries ===

  - id: loop-sgv-to-entries
    description: Loop SGV entry to Nightscout entries format
    source_system: Loop
    target_system: Nightscout
    input:
      glucoseValue: 120
      glucoseTrend: "Flat"
      date: 1706540096000
      deviceId: "Loop"
    transforms:
      - type: rename
        from: glucoseValue
        to: sgv
      - type: rename
        from: glucoseTrend
        to: direction
      - type: default
        field: type
        value: "sgv"
    expected:
      sgv: 120
      direction: "Flat"
      date: 1706540096000
      type: "sgv"

  # === AAPS → Nightscout Treatments ===

  - id: aaps-temp-basal-transform
    description: AAPS temp basal to Nightscout treatment
    source_system: AAPS
    target_system: Nightscout
    input:
      temporaryBasal:
        rate: 1.5
        durationInMinutes: 30
        isAbsolute: true
      timestamp: 1706540096000
      pumpSerial: "123456"
    transforms:
      - type: extract
        from: temporaryBasal.rate
        to: absolute
      - type: extract
        from: temporaryBasal.durationInMinutes
        to: duration
      - type: rename
        from: timestamp
        to: created_at
      - type: default
        field: eventType
        value: "Temp Basal"
    expected:
      absolute: 1.5
      duration: 30
      created_at: 1706540096000
      eventType: "Temp Basal"

  # === xDrip → Nightscout Entries ===

  - id: xdrip-bg-reading-transform
    description: xDrip+ BgReading to Nightscout entry
    source_system: xDrip
    target_system: Nightscout
    input:
      calculated_value: 115.5
      slope_name: "DoubleUp"
      timestamp: 1706540096000
      source: "G6 Native"
    transforms:
      - type: rename
        from: calculated_value
        to: sgv
      - type: rename
        from: slope_name
        to: direction
      - type: coerce
        field: sgv
        to_type: integer
      - type: default
        field: type
        value: "sgv"
    expected:
      sgv: 115
      direction: "DoubleUp"
      timestamp: 1706540096000
      type: "sgv"

  # === Nightscout DeviceStatus Extraction ===

  - id: devicestatus-iob-extraction
    description: Extract IOB from nested deviceStatus
    source_system: Nightscout
    target_system: Display
    input:
      device: "loop://iPhone"
      created_at: "2024-01-29T14:54:56.000Z"
      loop:
        iob:
          iob: 2.35
          timestamp: "2024-01-29T14:54:56.000Z"
        predicted:
          values: [120, 115, 110]
    transforms:
      - type: extract
        from: loop.iob.iob
        to: iob
      - type: extract
        from: loop.predicted.values[0]
        to: predictedBG
    expected:
      iob: 2.35
      predictedBG: 120
      device: "loop://iPhone"

  # === Trio Override Transform ===

  - id: trio-override-to-treatment
    description: Trio override to Nightscout treatment
    source_system: Trio
    target_system: Nightscout
    input:
      overrideName: "Exercise"
      targetRange:
        lower: 140
        upper: 160
      duration: 3600
      insulinNeedsScaleFactor: 0.8
    transforms:
      - type: rename
        from: overrideName
        to: reason
      - type: extract
        from: targetRange.lower
        to: targetBottom
      - type: extract
        from: targetRange.upper
        to: targetTop
      - type: compute
        to: durationMinutes
        expression: "${duration} / 60"
      - type: default
        field: eventType
        value: "Temporary Target"
    expected:
      reason: "Exercise"
      targetBottom: 140
      targetTop: 160
      durationMinutes: 60
      eventType: "Temporary Target"

  # === Type Coercion Tests ===

  - id: coerce-string-to-number
    description: Coerce string glucose to number
    source_system: any
    target_system: any
    input:
      sgv: "120"
      direction: "Flat"
    transforms:
      - type: coerce
        field: sgv
        to_type: number
    expected:
      sgv: 120.0
      direction: "Flat"

  - id: coerce-number-to-string
    description: Coerce numeric ID to string
    source_system: any
    target_system: any
    input:
      _id: 12345
      sgv: 120
    transforms:
      - type: coerce
        field: _id
        to_type: string
    expected:
      _id: "12345"
      sgv: 120
"""
    
    sample_path = TRANSFORMS_DIR / "transforms.yaml"
    with open(sample_path, "w") as f:
        f.write(sample)
    print(f"Created {sample_path}")


if __name__ == "__main__":
    sys.exit(main())
