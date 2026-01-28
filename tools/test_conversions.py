#!/usr/bin/env python3
"""
Unit Conversion Test Runner - validates cross-system unit transformations.

Usage:
    python tools/test_conversions.py                    # Run all tests
    python tools/test_conversions.py --id glucose-*    # Run matching tests
    python tools/test_conversions.py -v                # Verbose output

Exit codes:
    0 - All tests pass
    1 - Test failures
    2 - Configuration errors
"""

import argparse
import fnmatch
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

yaml: Any = None
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

WORKSPACE_ROOT = Path(__file__).parent.parent
CONVERSIONS_DIR = WORKSPACE_ROOT / "conformance" / "unit-conversions"

# Conversion factor for glucose units
GLUCOSE_FACTOR = 18.0182


class ConversionResult:
    def __init__(self, test_id: str, passed: bool, 
                 input_val: Any = None, expected: Any = None, 
                 actual: Any = None, message: str = ""):
        self.test_id = test_id
        self.passed = passed
        self.input_val = input_val
        self.expected = expected
        self.actual = actual
        self.message = message

    def __str__(self) -> str:
        status = "✓ PASS" if self.passed else "✗ FAIL"
        if self.passed:
            return f"{status} {self.test_id}"
        else:
            msg = self.message or f"expected {self.expected}, got {self.actual}"
            return f"{status} {self.test_id}: {msg}"


def convert_time(value: float, from_unit: str, to_unit: str) -> float:
    """Convert between time units."""
    # Normalize to milliseconds first
    ms_factors = {
        "milliseconds": 1,
        "seconds": 1000,
        "minutes": 60 * 1000,
        "hours": 60 * 60 * 1000,
    }
    
    if from_unit not in ms_factors or to_unit not in ms_factors:
        raise ValueError(f"Unknown time unit: {from_unit} or {to_unit}")
    
    ms_value = value * ms_factors[from_unit]
    return ms_value / ms_factors[to_unit]


def convert_glucose(value: float, from_unit: str, to_unit: str) -> float:
    """Convert between glucose units."""
    if from_unit == to_unit:
        return value
    
    if from_unit == "mg/dL" and to_unit == "mmol/L":
        return value / GLUCOSE_FACTOR
    elif from_unit == "mmol/L" and to_unit == "mg/dL":
        return value * GLUCOSE_FACTOR
    else:
        raise ValueError(f"Unknown glucose conversion: {from_unit} → {to_unit}")


def convert_isf(value: float, from_unit: str, to_unit: str) -> float:
    """Convert insulin sensitivity factor units."""
    if from_unit == to_unit:
        return value
    
    if from_unit == "mmol/L/U" and to_unit == "mg/dL/U":
        return value * GLUCOSE_FACTOR
    elif from_unit == "mg/dL/U" and to_unit == "mmol/L/U":
        return value / GLUCOSE_FACTOR
    else:
        raise ValueError(f"Unknown ISF conversion: {from_unit} → {to_unit}")


def convert_timestamp(value: Any, from_unit: str, to_unit: str) -> Any:
    """Convert between timestamp formats."""
    if from_unit == "epoch_ms" and to_unit == "iso8601":
        dt = datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{(value % 1000):03d}Z"
    elif from_unit == "epoch_s" and to_unit == "epoch_ms":
        return value * 1000
    elif from_unit == "iso8601" and to_unit == "epoch_ms":
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    else:
        raise ValueError(f"Unknown timestamp conversion: {from_unit} → {to_unit}")


def perform_conversion(test: dict) -> tuple[Any, Any]:
    """
    Perform the conversion specified in the test.
    Returns (expected, actual) values.
    """
    input_data = test["input"]
    expected_data = test["expected"]
    field = test.get("field", "unknown")
    
    input_value = input_data["value"]
    input_unit = input_data["unit"]
    expected_value = expected_data["value"]
    expected_unit = expected_data["unit"]
    
    # Choose conversion based on field type
    if field in ("absorptionTime", "duration"):
        actual = convert_time(input_value, input_unit, expected_unit)
    elif field == "glucose":
        actual = convert_glucose(input_value, input_unit, expected_unit)
    elif field == "isf":
        actual = convert_isf(input_value, input_unit, expected_unit)
    elif field == "timestamp":
        actual = convert_timestamp(input_value, input_unit, expected_unit)
    elif field in ("insulin", "carbs", "carbratio"):
        # Identity conversion - just check precision preservation
        actual = input_value
    else:
        # Default: identity
        actual = input_value
    
    return expected_value, actual


def compare_values(expected: Any, actual: Any, precision: int) -> bool:
    """Compare values with specified precision."""
    if isinstance(expected, str) and isinstance(actual, str):
        return expected == actual
    
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        # Round both to the specified precision
        factor = 10 ** precision
        rounded_expected = round(expected * factor) / factor
        rounded_actual = round(actual * factor) / factor
        return math.isclose(rounded_expected, rounded_actual, rel_tol=1e-9)
    
    return expected == actual


def run_test(test: dict) -> ConversionResult:
    """Run a single conversion test."""
    test_id = test.get("id", "unknown")
    precision = test.get("precision", 2)
    
    try:
        expected, actual = perform_conversion(test)
        passed = compare_values(expected, actual, precision)
        
        return ConversionResult(
            test_id=test_id,
            passed=passed,
            input_val=test["input"]["value"],
            expected=expected,
            actual=round(actual, precision) if isinstance(actual, float) else actual
        )
    except Exception as e:
        return ConversionResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}"
        )


def load_conversions(filepath: Path) -> list[dict]:
    """Load conversion test cases from YAML file."""
    if not filepath.exists():
        return []
    
    if not YAML_AVAILABLE:
        print(f"Warning: PyYAML not installed, cannot parse {filepath}", file=sys.stderr)
        return []
    
    try:
        with open(filepath) as f:
            data = yaml.safe_load(f)
            return data.get("conversions", [])
    except Exception as e:
        print(f"Error loading {filepath}: {e}", file=sys.stderr)
        return []


def discover_test_files() -> list[Path]:
    """Find all conversion test YAML files."""
    files = []
    if CONVERSIONS_DIR.exists():
        for path in CONVERSIONS_DIR.glob("*.yaml"):
            if not path.name.startswith("_"):
                files.append(path)
        for path in CONVERSIONS_DIR.glob("*.yml"):
            if not path.name.startswith("_"):
                files.append(path)
    return sorted(files)


def main():
    parser = argparse.ArgumentParser(description="Run unit conversion tests")
    parser.add_argument("--id", help="Filter tests by ID pattern (glob)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show all results")
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    args = parser.parse_args()

    if not YAML_AVAILABLE:
        print("Error: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
        return 2

    test_files = discover_test_files()
    if not test_files:
        print("No conversion test files found in conformance/unit-conversions/")
        return 0

    all_tests: list[dict] = []
    for filepath in test_files:
        tests = load_conversions(filepath)
        all_tests.extend(tests)

    # Filter by ID pattern if specified
    if args.id:
        all_tests = [t for t in all_tests if fnmatch.fnmatch(t.get("id", ""), args.id)]

    if not all_tests:
        print("No tests match the filter criteria")
        return 0

    print(f"Running {len(all_tests)} conversion tests...\n")

    results: list[ConversionResult] = []
    for test in all_tests:
        result = run_test(test)
        results.append(result)
        
        if args.verbose or not result.passed:
            print(result)

    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed

    print(f"\n{'─' * 40}")
    print(f"Results: {passed} passed, {failed} failed")

    if args.json:
        report = {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "tests": [
                {
                    "id": r.test_id,
                    "passed": r.passed,
                    "expected": r.expected,
                    "actual": r.actual,
                    "message": r.message
                }
                for r in results
            ]
        }
        print(json.dumps(report, indent=2))

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
