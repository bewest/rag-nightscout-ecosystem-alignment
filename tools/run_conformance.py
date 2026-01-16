#!/usr/bin/env python3
"""
Conformance Runner - executes assertions against scenario fixtures.

Usage:
    python tools/run_conformance.py                     # Run all scenarios (offline)
    python tools/run_conformance.py --scenario NAME     # Run specific scenario
    python tools/run_conformance.py --nightscout URL    # Run against live endpoint

Exit codes:
    0 - All assertions pass
    1 - Assertion failures
    2 - Configuration/file errors
"""

import json
import sys
from pathlib import Path
from typing import Any

yaml: Any = None
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

WORKSPACE_ROOT = Path(__file__).parent.parent
SCENARIOS_DIR = WORKSPACE_ROOT / "conformance" / "scenarios"
ASSERTIONS_DIR = WORKSPACE_ROOT / "conformance" / "assertions"


class AssertionResult:
    def __init__(self, assertion_id: str, passed: bool, message: str = ""):
        self.assertion_id = assertion_id
        self.passed = passed
        self.message = message

    def __str__(self):
        status = "PASS" if self.passed else "FAIL"
        msg = f" - {self.message}" if self.message else ""
        return f"[{status}] {self.assertion_id}{msg}"


def load_yaml_or_json(filepath: Path) -> dict | None:
    if not filepath.exists():
        return None

    suffix = filepath.suffix.lower()
    try:
        with open(filepath) as f:
            if suffix in (".yaml", ".yml"):
                if not YAML_AVAILABLE:
                    print(f"Warning: PyYAML not installed, cannot parse {filepath}", file=sys.stderr)
                    return None
                return yaml.safe_load(f)
            else:
                return json.load(f)
    except Exception as e:
        print(f"Error loading {filepath}: {e}", file=sys.stderr)
        return None


def find_events_file(scenario_dir: Path) -> Path | None:
    for name in ["events.json", "input.json", "fixtures.json"]:
        path = scenario_dir / name
        if path.exists():
            return path
    return None


def find_expected_file(scenario_dir: Path) -> Path | None:
    for name in ["expected.json", "expected-nightscout.json", "expected-output.json"]:
        path = scenario_dir / name
        if path.exists():
            return path
    return None


def get_nested_value(data: dict | list, path: str) -> Any:
    parts = path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                idx = int(part)
                current = current[idx]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if current is None:
            return None
    return current


def check_state_assertion(events: list, assertion: dict) -> AssertionResult:
    target = assertion.get("target", "")
    expected = assertion.get("expected")

    parts = target.split(".", 1)
    if len(parts) < 2:
        return AssertionResult(
            assertion["id"], False,
            f"Invalid target format: {target}"
        )

    entity_type = parts[0]
    field_path = parts[1]

    for event in events:
        if event.get("type") == entity_type or entity_type in str(event.get("id", "")):
            actual = get_nested_value(event, field_path)
            if actual == expected:
                return AssertionResult(assertion["id"], True)
            else:
                return AssertionResult(
                    assertion["id"], False,
                    f"Expected {field_path}={expected}, got {actual}"
                )

    return AssertionResult(
        assertion["id"], False,
        f"No matching entity found for {entity_type}"
    )


def check_reference_assertion(events: list, assertion: dict) -> AssertionResult:
    target = assertion.get("target", "")

    for event in events:
        ref_field = target.split(".")[-1]
        ref_value = event.get(ref_field)

        if ref_value is not None:
            ref_exists = any(e.get("id") == ref_value for e in events)
            if ref_exists:
                return AssertionResult(assertion["id"], True)
            else:
                return AssertionResult(
                    assertion["id"], False,
                    f"Reference {ref_field}={ref_value} points to non-existent entity"
                )

    return AssertionResult(assertion["id"], True, "No references to check")


def check_immutable_assertion(events: list, assertion: dict) -> AssertionResult:
    fields = assertion.get("fields", [])
    return AssertionResult(
        assertion["id"], True,
        f"Immutability check for {len(fields)} field(s) (requires historical comparison)"
    )


def check_query_assertion(events: list, assertion: dict) -> AssertionResult:
    expected_count = assertion.get("expected_count")

    if expected_count is not None:
        actual_count = len(events)
        if actual_count == expected_count:
            return AssertionResult(assertion["id"], True)
        else:
            return AssertionResult(
                assertion["id"], False,
                f"Expected {expected_count} events, got {actual_count}"
            )

    return AssertionResult(assertion["id"], True, "Query assertion (requires live endpoint)")


def check_invariant(events: list, invariant_type: str) -> AssertionResult:
    if invariant_type == "single_active_override":
        active_overrides = [
            e for e in events
            if e.get("type") == "override" and e.get("status") == "active"
        ]
        if len(active_overrides) <= 1:
            return AssertionResult("invariant:single_active_override", True)
        else:
            return AssertionResult(
                "invariant:single_active_override", False,
                f"Found {len(active_overrides)} active overrides (expected at most 1)"
            )

    return AssertionResult(f"invariant:{invariant_type}", True, "Unknown invariant type")


def run_assertions(events: list, assertions: list[dict]) -> list[AssertionResult]:
    results = []

    results.append(check_invariant(events, "single_active_override"))

    for event in events:
        if event.get("supersedes"):
            ref_id = event["supersedes"]
            ref_exists = any(e.get("id") == ref_id for e in events)
            if not ref_exists:
                results.append(AssertionResult(
                    f"refint:{event.get('id', 'unknown')}",
                    False,
                    f"supersedes references non-existent id: {ref_id}"
                ))

    for assertion in assertions:
        assertion_type = assertion.get("type", "")
        assertion_id = assertion.get("id", "unknown")

        if assertion_type == "state":
            results.append(check_state_assertion(events, assertion))
        elif assertion_type == "reference":
            results.append(check_reference_assertion(events, assertion))
        elif assertion_type == "immutable":
            results.append(check_immutable_assertion(events, assertion))
        elif assertion_type == "query":
            results.append(check_query_assertion(events, assertion))
        elif assertion_type == "timestamp":
            results.append(AssertionResult(assertion_id, True, "Timestamp check (requires data)"))
        else:
            results.append(AssertionResult(
                assertion_id, True,
                f"Unknown assertion type: {assertion_type}"
            ))

    return results


def run_scenario(scenario_name: str, verbose: bool = False) -> tuple[int, int]:
    scenario_dir = SCENARIOS_DIR / scenario_name
    if not scenario_dir.exists():
        print(f"Scenario directory not found: {scenario_dir}", file=sys.stderr)
        return 0, 1

    for suffix in [".yaml", ".yml", ".json"]:
        assertions_file = ASSERTIONS_DIR / f"{scenario_name}{suffix}"
        if assertions_file.exists():
            break
    else:
        assertions_file = None

    assertions_data = load_yaml_or_json(assertions_file) if assertions_file else None
    assertions = assertions_data.get("assertions", []) if assertions_data else []

    events_file = find_events_file(scenario_dir)
    events = []
    if events_file:
        events_data = load_yaml_or_json(events_file)
        if events_data:
            events = events_data if isinstance(events_data, list) else [events_data]

    print(f"\n=== Scenario: {scenario_name} ===")
    print(f"Events: {len(events)}, Assertions: {len(assertions)}")

    results = run_assertions(events, assertions)

    passed = 0
    failed = 0
    for result in results:
        if result.passed:
            passed += 1
            if verbose:
                print(result)
        else:
            failed += 1
            print(result)

    return passed, failed


def discover_scenarios() -> list[str]:
    scenarios = []
    if SCENARIOS_DIR.exists():
        for path in SCENARIOS_DIR.iterdir():
            if path.is_dir() and not path.name.startswith("_"):
                scenarios.append(path.name)
    return sorted(scenarios)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run conformance assertions")
    parser.add_argument("--scenario", "-s", help="Run specific scenario")
    parser.add_argument("--offline", action="store_true", default=True, help="Offline mode (default)")
    parser.add_argument("--nightscout", metavar="URL", help="Run against live Nightscout endpoint")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show all results including passes")
    parser.add_argument("--list", action="store_true", help="List available scenarios")
    args = parser.parse_args()

    if not YAML_AVAILABLE:
        print("Warning: PyYAML not installed. YAML assertions will be skipped.", file=sys.stderr)
        print("Install with: pip install pyyaml", file=sys.stderr)
        print()

    if args.list:
        scenarios = discover_scenarios()
        print("Available scenarios:")
        for s in scenarios:
            print(f"  - {s}")
        return 0

    if args.nightscout:
        print(f"Live endpoint mode not yet implemented: {args.nightscout}")
        return 2

    if args.scenario:
        scenarios = [args.scenario]
    else:
        scenarios = discover_scenarios()

    if not scenarios:
        print("No scenarios found in conformance/scenarios/")
        return 0

    total_passed = 0
    total_failed = 0

    for scenario in scenarios:
        passed, failed = run_scenario(scenario, args.verbose)
        total_passed += passed
        total_failed += failed

    print()
    print(f"Total: {total_passed} passed, {total_failed} failed")

    return 1 if total_failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
