#!/usr/bin/env python3
"""
Assertion Tracer - maps assertions to requirements and identifies coverage gaps.

Parses conformance assertion files and traces them back to requirements,
identifying:
1. Assertions with no linked requirements
2. Requirements with no assertions
3. Gaps referenced by assertions but not addressed

Usage:
    python tools/verify_assertions.py              # Full analysis
    python tools/verify_assertions.py --json       # Output JSON only
    python tools/verify_assertions.py --orphans    # Focus on orphaned assertions

Outputs:
    traceability/assertion-trace.json  - Machine-readable trace report
    traceability/assertion-trace.md    - Human-readable trace report
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    yaml = None  # type: ignore[assignment]
    HAS_YAML = False

WORKSPACE_ROOT = Path(__file__).parent.parent
CONFORMANCE_DIR = WORKSPACE_ROOT / "conformance"
ASSERTIONS_DIR = CONFORMANCE_DIR / "assertions"
TRACEABILITY_DIR = WORKSPACE_ROOT / "traceability"

REQ_PATTERN = re.compile(r'\b(REQ-(?:[A-Z]+-)?[0-9]{2,3})\b')
GAP_PATTERN = re.compile(r'\b(GAP-[A-Z]+-\d{3})\b')


def parse_yaml_file(filepath):
    """Parse a YAML file, with fallback to regex if PyYAML not available."""
    content = filepath.read_text(errors="ignore")
    
    if HAS_YAML and yaml is not None:
        try:
            return yaml.safe_load(content), content
        except Exception:
            pass
    
    return None, content


def extract_assertions(filepath):
    """Extract assertion definitions from a YAML file."""
    assertions = []
    
    data, content = parse_yaml_file(filepath)
    rel_path = str(filepath.relative_to(WORKSPACE_ROOT))
    
    if data and isinstance(data, dict):
        # Get scenario-level requirements and gaps (applies to all assertions in file)
        scenario_requirements = data.get("requirements", [])
        scenario_gaps = data.get("related_gaps", [])
        
        assertions_data = data.get("assertions", {})
        if isinstance(assertions_data, dict):
            for key, value in assertions_data.items():
                if isinstance(value, dict):
                    # Merge scenario-level requirements with assertion-level
                    assertion_reqs = value.get("requirements", [])
                    all_reqs = list(set(scenario_requirements + assertion_reqs))
                    assertion_gaps = value.get("related_gaps", [])
                    all_gaps = list(set(scenario_gaps + assertion_gaps))
                    
                    assertions.append({
                        "id": key,
                        "file": rel_path,
                        "title": value.get("title", key),
                        "description": value.get("description", ""),
                        "requirements": all_reqs,
                        "related_gaps": all_gaps,
                        "tests": list(value.get("tests", {}).keys()) if isinstance(value.get("tests"), dict) else []
                    })
        elif isinstance(assertions_data, list):
            for item in assertions_data:
                if isinstance(item, dict):
                    # Merge scenario-level requirements with assertion-level
                    assertion_reqs = item.get("requirements", [])
                    all_reqs = list(set(scenario_requirements + assertion_reqs))
                    assertion_gaps = item.get("related_gaps", [])
                    all_gaps = list(set(scenario_gaps + assertion_gaps))
                    
                    assertions.append({
                        "id": item.get("id", filepath.stem),
                        "file": rel_path,
                        "title": item.get("title", ""),
                        "description": item.get("description", ""),
                        "requirements": all_reqs,
                        "related_gaps": all_gaps,
                        "tests": list(item.get("tests", {}).keys()) if isinstance(item.get("tests"), dict) else []
                    })
    
    else:
        reqs = REQ_PATTERN.findall(content)
        gaps = GAP_PATTERN.findall(content)
        
        if reqs or gaps:
            assertions.append({
                "id": filepath.stem,
                "file": rel_path,
                "title": filepath.stem.replace('-', ' ').title(),
                "requirements": list(set(reqs)),
                "related_gaps": list(set(gaps)),
                "tests": [],
                "parsed_via": "regex"
            })
    
    return assertions


def extract_requirements_list(traceability_dir):
    """Extract requirement IDs from all *-requirements.md files."""
    requirements = set()
    
    if not traceability_dir.exists():
        return requirements
    
    # Scan all requirements files in traceability directory
    for req_file in traceability_dir.glob("*-requirements.md"):
        content = req_file.read_text(errors="ignore")
        for match in REQ_PATTERN.finditer(content):
            requirements.add(match.group(1))
    
    # Also check the main requirements.md
    main_file = traceability_dir / "requirements.md"
    if main_file.exists():
        content = main_file.read_text(errors="ignore")
        for match in REQ_PATTERN.finditer(content):
            requirements.add(match.group(1))
    
    return requirements


def extract_gaps_list(traceability_dir):
    """Extract gap IDs from all *-gaps.md files."""
    gaps = set()
    
    if not traceability_dir.exists():
        return gaps
    
    # Scan all gap files in traceability directory
    for gap_file in traceability_dir.glob("*-gaps.md"):
        content = gap_file.read_text(errors="ignore")
        for match in GAP_PATTERN.finditer(content):
            gaps.add(match.group(1))
    
    # Also check the main gaps.md
    main_file = traceability_dir / "gaps.md"
    if main_file.exists():
        content = main_file.read_text(errors="ignore")
        for match in GAP_PATTERN.finditer(content):
            gaps.add(match.group(1))
    
    return gaps


def analyze_traces(assertions, known_requirements, known_gaps):
    """Analyze assertion-to-requirement traces."""
    req_to_assertions = defaultdict(list)
    gap_to_assertions = defaultdict(list)
    
    orphaned_assertions = []
    unknown_requirements = set()
    unknown_gaps = set()
    
    for assertion in assertions:
        assertion_id = assertion["id"]
        assertion_file = assertion["file"]
        
        reqs = assertion.get("requirements", [])
        gaps = assertion.get("related_gaps", [])
        
        if not reqs and not gaps:
            orphaned_assertions.append(assertion)
        
        for req in reqs:
            req_to_assertions[req].append({
                "assertion_id": assertion_id,
                "file": assertion_file,
                "title": assertion.get("title", "")
            })
            if req not in known_requirements:
                unknown_requirements.add(req)
        
        for gap in gaps:
            gap_to_assertions[gap].append({
                "assertion_id": assertion_id,
                "file": assertion_file,
                "title": assertion.get("title", "")
            })
            if gap not in known_gaps:
                unknown_gaps.add(gap)
    
    uncovered_requirements = [
        req for req in known_requirements
        if req not in req_to_assertions
    ]
    
    uncovered_gaps = [
        gap for gap in known_gaps
        if gap not in gap_to_assertions
    ]
    
    return {
        "req_to_assertions": dict(req_to_assertions),
        "gap_to_assertions": dict(gap_to_assertions),
        "orphaned_assertions": orphaned_assertions,
        "unknown_requirements": list(unknown_requirements),
        "unknown_gaps": list(unknown_gaps),
        "uncovered_requirements": sorted(uncovered_requirements),
        "uncovered_gaps": sorted(uncovered_gaps)
    }


def generate_report(assertions, traces, known_requirements, known_gaps):
    """Generate the trace report."""
    total_tests = sum(len(a.get("tests", [])) for a in assertions)
    
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_assertions": len(assertions),
            "total_tests": total_tests,
            "known_requirements": len(known_requirements),
            "known_gaps": len(known_gaps),
            "requirements_with_assertions": len(traces["req_to_assertions"]),
            "gaps_with_assertions": len(traces["gap_to_assertions"]),
            "orphaned_assertions": len(traces["orphaned_assertions"]),
            "uncovered_requirements": len(traces["uncovered_requirements"]),
            "uncovered_gaps": len(traces["uncovered_gaps"]),
            "unknown_references": len(traces["unknown_requirements"]) + len(traces["unknown_gaps"])
        },
        "assertions": assertions,
        "traces": traces
    }
    
    return report


def generate_markdown(report):
    """Generate human-readable markdown report."""
    lines = [
        "# Assertion Trace Report",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Assertion Groups | {report['summary']['total_assertions']} |",
        f"| Total Test Cases | {report['summary']['total_tests']} |",
        f"| Known Requirements | {report['summary']['known_requirements']} |",
        f"| Requirements with Assertions | {report['summary']['requirements_with_assertions']} |",
        f"| Uncovered Requirements | {report['summary']['uncovered_requirements']} |",
        f"| Known Gaps | {report['summary']['known_gaps']} |",
        f"| Gaps with Assertions | {report['summary']['gaps_with_assertions']} |",
        f"| Orphaned Assertions | {report['summary']['orphaned_assertions']} |",
        "",
    ]
    
    coverage_pct = 0
    if report['summary']['known_requirements'] > 0:
        coverage_pct = (report['summary']['requirements_with_assertions'] / 
                       report['summary']['known_requirements']) * 100
    
    lines.extend([
        f"**Requirement Coverage: {coverage_pct:.1f}%**",
        ""
    ])
    
    if report["traces"]["uncovered_requirements"]:
        lines.extend([
            "## Uncovered Requirements",
            "",
            "These requirements have no assertions:",
            ""
        ])
        for req in report["traces"]["uncovered_requirements"][:20]:
            lines.append(f"- {req}")
        if len(report["traces"]["uncovered_requirements"]) > 20:
            lines.append(f"- ... and {len(report['traces']['uncovered_requirements']) - 20} more")
        lines.append("")
    
    if report["traces"]["orphaned_assertions"]:
        lines.extend([
            "## Orphaned Assertions",
            "",
            "These assertions have no linked requirements or gaps:",
            ""
        ])
        for assertion in report["traces"]["orphaned_assertions"]:
            lines.append(f"- **{assertion['id']}** (`{assertion['file']}`)")
        lines.append("")
    
    if report["traces"]["unknown_requirements"] or report["traces"]["unknown_gaps"]:
        lines.extend([
            "## Unknown References",
            "",
            "These IDs are referenced in assertions but not defined:",
            ""
        ])
        for ref in report["traces"]["unknown_requirements"]:
            lines.append(f"- {ref} (requirement)")
        for ref in report["traces"]["unknown_gaps"]:
            lines.append(f"- {ref} (gap)")
        lines.append("")
    
    lines.extend([
        "## Assertions by File",
        "",
        "| File | Assertions | Tests | Requirements | Gaps |",
        "|----|------------|-------|--------------|------|"
    ])
    
    by_file = {}
    for a in report["assertions"]:
        f = a["file"]
        if f not in by_file:
            by_file[f] = {"assertions": 0, "tests": 0, "reqs": set(), "gaps": set()}
        by_file[f]["assertions"] += 1
        by_file[f]["tests"] += len(a.get("tests", []))
        by_file[f]["reqs"].update(a.get("requirements", []))
        by_file[f]["gaps"].update(a.get("related_gaps", []))
    
    for f, data in sorted(by_file.items()):
        lines.append(f"| `{f}` | {data['assertions']} | {data['tests']} | {len(data['reqs'])} | {len(data['gaps'])} |")
    
    lines.append("")
    
    lines.extend([
        "## Requirement to Assertion Mapping",
        "",
        "| Requirement | Assertions |",
        "|-------------|------------|"
    ])
    
    for req, assertions in sorted(report["traces"]["req_to_assertions"].items()):
        assertion_list = ", ".join(a["assertion_id"] for a in assertions[:3])
        if len(assertions) > 3:
            assertion_list += f" (+{len(assertions)-3})"
        lines.append(f"| {req} | {assertion_list} |")
    
    lines.append("")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Trace assertions to requirements")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    parser.add_argument("--orphans", action="store_true", help="Focus on orphaned assertions")
    parser.add_argument("--no-write", action="store_true", help="Don't write output files")
    args = parser.parse_args()
    
    if not HAS_YAML:
        print("Note: PyYAML not installed, using regex-based parsing")
    
    print("Extracting assertions...")
    all_assertions = []
    
    if ASSERTIONS_DIR.exists():
        for filepath in ASSERTIONS_DIR.glob("*.yaml"):
            if filepath.name.startswith('_'):
                continue
            assertions = extract_assertions(filepath)
            all_assertions.extend(assertions)
    
    print(f"  Found {len(all_assertions)} assertion groups")
    
    print("Loading known requirements and gaps...")
    known_requirements = extract_requirements_list(TRACEABILITY_DIR)
    known_gaps = extract_gaps_list(TRACEABILITY_DIR)
    print(f"  {len(known_requirements)} requirements, {len(known_gaps)} gaps")
    
    print("Analyzing traces...")
    traces = analyze_traces(all_assertions, known_requirements, known_gaps)
    
    report = generate_report(all_assertions, traces, known_requirements, known_gaps)
    
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"\nAssertion Trace Summary:")
        print(f"  Assertion groups: {report['summary']['total_assertions']}")
        print(f"  Test cases: {report['summary']['total_tests']}")
        print(f"  Requirements covered: {report['summary']['requirements_with_assertions']}/{report['summary']['known_requirements']}")
        print(f"  Orphaned assertions: {report['summary']['orphaned_assertions']}")
        print(f"  Uncovered requirements: {report['summary']['uncovered_requirements']}")
    
    if not args.no_write:
        TRACEABILITY_DIR.mkdir(parents=True, exist_ok=True)
        
        json_path = TRACEABILITY_DIR / "assertion-trace.json"
        with open(json_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nWrote: {json_path}")
        
        md_path = TRACEABILITY_DIR / "assertion-trace.md"
        with open(md_path, "w") as f:
            f.write(generate_markdown(report))
        print(f"Wrote: {md_path}")
    
    issues = (report['summary']['orphaned_assertions'] + 
              report['summary']['unknown_references'])
    return 1 if issues > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
