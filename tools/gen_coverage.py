#!/usr/bin/env python3
"""
Coverage Matrix Generator - generates coverage status from filesystem state.

Usage:
    python tools/gen_coverage.py           # Generate coverage matrix
    python tools/gen_coverage.py --json    # Output JSON only
    python tools/gen_coverage.py --md      # Output Markdown only

Outputs:
    traceability/coverage-matrix.json  - Machine-readable coverage data
    traceability/coverage-matrix.md    - Human-readable coverage report
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

WORKSPACE_ROOT = Path(__file__).parent.parent
SCENARIOS_DIR = WORKSPACE_ROOT / "conformance" / "scenarios"
ASSERTIONS_DIR = WORKSPACE_ROOT / "conformance" / "assertions"
SPECS_DIR = WORKSPACE_ROOT / "specs"
MAPPING_DIR = WORKSPACE_ROOT / "mapping"
TRACEABILITY_DIR = WORKSPACE_ROOT / "traceability"

PROJECTS = ["nightscout", "aaps", "loop", "trio"]


def check_file_exists(path: Path) -> bool:
    return path.exists() and path.is_file()


def check_dir_has_files(path: Path, pattern: str = "*") -> bool:
    if not path.exists():
        return False
    return any(path.glob(pattern))


def find_assertions_file(scenario_name: str) -> Path | None:
    for suffix in [".yaml", ".yml", ".json"]:
        path = ASSERTIONS_DIR / f"{scenario_name}{suffix}"
        if path.exists():
            return path
    return None


def find_requirements_file(scenario_dir: Path) -> Path | None:
    for name in ["requirements.json", "requirements.yaml", "requirements.md"]:
        path = scenario_dir / name
        if path.exists():
            return path
    return None


def check_mapping_coverage(scenario_name: str, project: str) -> dict:
    mapping_dir = MAPPING_DIR / project
    if not mapping_dir.exists():
        return {"status": "missing", "file": None}

    for suffix in [".md", ".json", ".yaml"]:
        path = mapping_dir / f"{scenario_name}{suffix}"
        if path.exists():
            content = path.read_text()
            if len(content.strip()) > 50:
                return {"status": "documented", "file": str(path.relative_to(WORKSPACE_ROOT))}
            else:
                return {"status": "stub", "file": str(path.relative_to(WORKSPACE_ROOT))}

    return {"status": "missing", "file": None}


def analyze_scenario(scenario_name: str) -> dict:
    scenario_dir = SCENARIOS_DIR / scenario_name
    result = {
        "name": scenario_name,
        "path": str(scenario_dir.relative_to(WORKSPACE_ROOT)),
        "has_requirements": False,
        "has_assertions": False,
        "has_schema_link": False,
        "has_fixtures": False,
        "project_coverage": {},
        "coverage_score": 0.0,
        "status": "incomplete"
    }

    req_file = find_requirements_file(scenario_dir)
    if req_file:
        result["has_requirements"] = True
        result["requirements_file"] = str(req_file.relative_to(WORKSPACE_ROOT))

    assertions_file = find_assertions_file(scenario_name)
    if assertions_file:
        result["has_assertions"] = True
        result["assertions_file"] = str(assertions_file.relative_to(WORKSPACE_ROOT))

    for json_file in scenario_dir.glob("*.json"):
        if "requirement" not in json_file.name.lower():
            result["has_fixtures"] = True
            break

    readme = scenario_dir / "README.md"
    if readme.exists():
        content = readme.read_text()
        if "schema" in content.lower() or "jsonschema" in content.lower():
            result["has_schema_link"] = True

    for project in PROJECTS:
        result["project_coverage"][project] = check_mapping_coverage(scenario_name, project)

    score_components = [
        result["has_requirements"],
        result["has_assertions"],
        result["has_fixtures"],
        result["has_schema_link"]
    ]
    base_score = sum(score_components) / len(score_components)

    project_scores = []
    for project, coverage in result["project_coverage"].items():
        if coverage["status"] == "documented":
            project_scores.append(1.0)
        elif coverage["status"] == "stub":
            project_scores.append(0.5)
        else:
            project_scores.append(0.0)

    if project_scores:
        project_avg = sum(project_scores) / len(project_scores)
        result["coverage_score"] = round((base_score * 0.6) + (project_avg * 0.4), 2)
    else:
        result["coverage_score"] = round(base_score * 0.6, 2)

    if result["coverage_score"] >= 0.8:
        result["status"] = "complete"
    elif result["coverage_score"] >= 0.5:
        result["status"] = "partial"
    else:
        result["status"] = "incomplete"

    return result


def discover_scenarios() -> list[str]:
    scenarios = []
    if SCENARIOS_DIR.exists():
        for path in SCENARIOS_DIR.iterdir():
            if path.is_dir() and not path.name.startswith("_"):
                scenarios.append(path.name)
    return sorted(scenarios)


def generate_coverage_matrix() -> dict:
    scenarios = discover_scenarios()
    matrix = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenarios": [],
        "summary": {
            "total": len(scenarios),
            "complete": 0,
            "partial": 0,
            "incomplete": 0,
            "average_score": 0.0
        },
        "projects": PROJECTS
    }

    total_score = 0.0
    for scenario_name in scenarios:
        analysis = analyze_scenario(scenario_name)
        matrix["scenarios"].append(analysis)

        matrix["summary"][analysis["status"]] += 1
        total_score += analysis["coverage_score"]

    if scenarios:
        matrix["summary"]["average_score"] = round(total_score / len(scenarios), 2)

    return matrix


def render_status_emoji(status: str) -> str:
    return {
        "complete": "[x]",
        "partial": "[~]",
        "incomplete": "[ ]",
        "documented": "[x]",
        "stub": "[~]",
        "missing": "[ ]"
    }.get(status, "[ ]")


def generate_markdown(matrix: dict) -> str:
    lines = [
        "# Coverage Matrix",
        "",
        f"Generated: {matrix['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Total scenarios: {matrix['summary']['total']}",
        f"- Complete: {matrix['summary']['complete']}",
        f"- Partial: {matrix['summary']['partial']}",
        f"- Incomplete: {matrix['summary']['incomplete']}",
        f"- Average coverage: {matrix['summary']['average_score']:.0%}",
        "",
        "## Scenarios",
        "",
        "| Scenario | Reqs | Assert | Fixtures | Schema | " + " | ".join(p.capitalize() for p in PROJECTS) + " | Score |",
        "|----------|------|--------|----------|--------|" + "|".join(["------"] * len(PROJECTS)) + "|-------|"
    ]

    for scenario in matrix["scenarios"]:
        row = [
            scenario["name"],
            render_status_emoji("complete" if scenario["has_requirements"] else "incomplete"),
            render_status_emoji("complete" if scenario["has_assertions"] else "incomplete"),
            render_status_emoji("complete" if scenario["has_fixtures"] else "incomplete"),
            render_status_emoji("complete" if scenario["has_schema_link"] else "incomplete")
        ]

        for project in PROJECTS:
            coverage = scenario["project_coverage"].get(project, {})
            row.append(render_status_emoji(coverage.get("status", "missing")))

        row.append(f"{scenario['coverage_score']:.0%}")
        lines.append("| " + " | ".join(row) + " |")

    lines.extend([
        "",
        "## Legend",
        "",
        "- `[x]` Complete/Documented",
        "- `[~]` Partial/Stub",
        "- `[ ]` Missing/Incomplete",
        "",
        "## Coverage Criteria",
        "",
        "A scenario is considered **complete** when it has:",
        "1. Requirements definition",
        "2. Assertions file",
        "3. Test fixtures",
        "4. Schema link in README",
        "5. Mapping notes for each project",
        ""
    ])

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate coverage matrix")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    parser.add_argument("--md", action="store_true", help="Output Markdown only")
    parser.add_argument("--stdout", action="store_true", help="Print to stdout instead of writing files")
    args = parser.parse_args()

    matrix = generate_coverage_matrix()

    if args.stdout:
        if args.json:
            print(json.dumps(matrix, indent=2))
        elif args.md:
            print(generate_markdown(matrix))
        else:
            print(json.dumps(matrix, indent=2))
            print("\n---\n")
            print(generate_markdown(matrix))
        return 0

    TRACEABILITY_DIR.mkdir(parents=True, exist_ok=True)

    if not args.md:
        json_path = TRACEABILITY_DIR / "coverage-matrix.json"
        with open(json_path, "w") as f:
            json.dump(matrix, f, indent=2)
        print(f"Written: {json_path}")

    if not args.json:
        md_path = TRACEABILITY_DIR / "coverage-matrix.md"
        with open(md_path, "w") as f:
            f.write(generate_markdown(matrix))
        print(f"Written: {md_path}")

    print()
    print(f"Coverage Summary:")
    print(f"  Total: {matrix['summary']['total']} scenarios")
    print(f"  Complete: {matrix['summary']['complete']}")
    print(f"  Partial: {matrix['summary']['partial']}")
    print(f"  Incomplete: {matrix['summary']['incomplete']}")
    print(f"  Average: {matrix['summary']['average_score']:.0%}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
