#!/usr/bin/env python3
"""
Workspace Inventory Generator - produces consolidated inventory of all artifacts.

Usage:
    python tools/gen_inventory.py           # Generate full inventory
    python tools/gen_inventory.py --json    # Output JSON only
    python tools/gen_inventory.py --md      # Output Markdown only

Outputs:
    traceability/inventory.json  - Machine-readable inventory
    traceability/inventory.md    - Human-readable inventory report
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).parent.parent
MAPPING_DIR = WORKSPACE_ROOT / "mapping"
SPECS_DIR = WORKSPACE_ROOT / "specs"
CONFORMANCE_DIR = WORKSPACE_ROOT / "conformance"
TRACEABILITY_DIR = WORKSPACE_ROOT / "traceability"
DOCS_DIR = WORKSPACE_ROOT / "docs"
REQUIREMENTS_FILE = TRACEABILITY_DIR / "requirements.md"


def scan_mapping_documents() -> dict:
    """Scan mapping/ directory for analysis documents by project."""
    projects = {}
    if not MAPPING_DIR.exists():
        return projects

    for project_dir in sorted(MAPPING_DIR.iterdir()):
        if not project_dir.is_dir() or project_dir.name.startswith("_"):
            continue

        project_name = project_dir.name
        documents = []

        for doc in sorted(project_dir.rglob("*.md")):
            rel_path = doc.relative_to(WORKSPACE_ROOT)
            content = doc.read_text(errors="ignore")
            word_count = len(content.split())
            has_code_refs = bool(re.search(r"`[a-zA-Z]+:[^`]+`", content))
            documents.append({
                "path": str(rel_path),
                "name": doc.stem,
                "word_count": word_count,
                "has_code_refs": has_code_refs,
                "status": "stub" if word_count < 100 else "documented"
            })

        if documents:
            projects[project_name] = {
                "document_count": len(documents),
                "documents": documents
            }

    return projects


def scan_specs() -> dict:
    """Scan specs/ directory for schema and API definitions."""
    specs = {
        "openapi": [],
        "jsonschema": [],
        "shape": []
    }

    if not SPECS_DIR.exists():
        return specs

    for spec_type in ["openapi", "jsonschema", "shape"]:
        type_dir = SPECS_DIR / spec_type
        if not type_dir.exists():
            continue

        for ext in ["*.yaml", "*.yml", "*.json"]:
            for spec_file in sorted(type_dir.rglob(ext)):
                rel_path = spec_file.relative_to(WORKSPACE_ROOT)
                specs[spec_type].append({
                    "path": str(rel_path),
                    "name": spec_file.stem
                })

    return specs


def scan_conformance() -> dict:
    """Scan conformance/ directory for scenarios and assertions."""
    conformance = {
        "scenarios": [],
        "assertions": []
    }

    scenarios_dir = CONFORMANCE_DIR / "scenarios"
    if scenarios_dir.exists():
        for scenario_dir in sorted(scenarios_dir.iterdir()):
            if scenario_dir.is_dir() and not scenario_dir.name.startswith("_"):
                readme = scenario_dir / "README.md"
                fixtures = list(scenario_dir.glob("*.json"))
                conformance["scenarios"].append({
                    "name": scenario_dir.name,
                    "path": str(scenario_dir.relative_to(WORKSPACE_ROOT)),
                    "has_readme": readme.exists(),
                    "fixture_count": len([f for f in fixtures if "requirement" not in f.name.lower()])
                })

    assertions_dir = CONFORMANCE_DIR / "assertions"
    if assertions_dir.exists():
        for ext in ["*.yaml", "*.yml", "*.json"]:
            for assertion_file in sorted(assertions_dir.glob(ext)):
                conformance["assertions"].append({
                    "name": assertion_file.stem,
                    "path": str(assertion_file.relative_to(WORKSPACE_ROOT))
                })

    return conformance


def extract_requirements() -> list:
    """Extract REQ-XXX identifiers from requirements.md."""
    requirements = []

    if not REQUIREMENTS_FILE.exists():
        return requirements

    content = REQUIREMENTS_FILE.read_text(errors="ignore")
    pattern = r"###\s+(REQ-\d+):\s*([^\n]+)"

    for match in re.finditer(pattern, content):
        req_id = match.group(1)
        req_title = match.group(2).strip()
        requirements.append({
            "id": req_id,
            "title": req_title
        })

    return requirements


def scan_docs() -> list:
    """Scan docs/ directory for additional documentation."""
    docs = []

    if not DOCS_DIR.exists():
        return docs

    for doc in sorted(DOCS_DIR.rglob("*.md")):
        if "_generated" in str(doc):
            continue
        rel_path = doc.relative_to(WORKSPACE_ROOT)
        docs.append({
            "path": str(rel_path),
            "name": doc.stem
        })

    return docs


def generate_inventory() -> dict:
    """Generate complete workspace inventory."""
    mapping = scan_mapping_documents()
    specs = scan_specs()
    conformance = scan_conformance()
    requirements = extract_requirements()
    docs = scan_docs()

    total_mapping_docs = sum(p["document_count"] for p in mapping.values())
    total_specs = sum(len(s) for s in specs.values())

    inventory = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "mapping_projects": len(mapping),
            "mapping_documents": total_mapping_docs,
            "specs_total": total_specs,
            "specs_openapi": len(specs["openapi"]),
            "specs_jsonschema": len(specs["jsonschema"]),
            "specs_shape": len(specs["shape"]),
            "scenarios": len(conformance["scenarios"]),
            "assertions": len(conformance["assertions"]),
            "requirements": len(requirements),
            "docs": len(docs)
        },
        "mapping": mapping,
        "specs": specs,
        "conformance": conformance,
        "requirements": requirements,
        "docs": docs
    }

    return inventory


def generate_markdown(inventory: dict) -> str:
    """Render inventory as Markdown."""
    lines = [
        "# Workspace Inventory",
        "",
        f"Generated: {inventory['generated_at']}",
        "",
        "## Summary",
        "",
        f"| Category | Count |",
        f"|----------|-------|",
        f"| Mapping Projects | {inventory['summary']['mapping_projects']} |",
        f"| Mapping Documents | {inventory['summary']['mapping_documents']} |",
        f"| OpenAPI Specs | {inventory['summary']['specs_openapi']} |",
        f"| JSON Schemas | {inventory['summary']['specs_jsonschema']} |",
        f"| Shape Specs | {inventory['summary']['specs_shape']} |",
        f"| Scenarios | {inventory['summary']['scenarios']} |",
        f"| Assertions | {inventory['summary']['assertions']} |",
        f"| Requirements | {inventory['summary']['requirements']} |",
        f"| Documentation Files | {inventory['summary']['docs']} |",
        "",
        "---",
        "",
        "## Mapping Documents by Project",
        ""
    ]

    for project, data in sorted(inventory["mapping"].items()):
        lines.append(f"### {project} ({data['document_count']} documents)")
        lines.append("")
        for doc in data["documents"]:
            status = "[x]" if doc["status"] == "documented" else "[~]"
            code_ref = " (has code refs)" if doc["has_code_refs"] else ""
            lines.append(f"- {status} [{doc['name']}]({doc['path']}){code_ref}")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## Specifications",
        ""
    ])

    for spec_type in ["openapi", "jsonschema", "shape"]:
        spec_list = inventory["specs"].get(spec_type, [])
        if spec_list:
            lines.append(f"### {spec_type.replace('_', ' ').title()} ({len(spec_list)})")
            lines.append("")
            for spec in spec_list:
                lines.append(f"- [{spec['name']}]({spec['path']})")
            lines.append("")

    lines.extend([
        "---",
        "",
        "## Conformance",
        "",
        "### Scenarios",
        ""
    ])

    for scenario in inventory["conformance"]["scenarios"]:
        readme = "[x]" if scenario["has_readme"] else "[ ]"
        lines.append(f"- {readme} [{scenario['name']}]({scenario['path']}) ({scenario['fixture_count']} fixtures)")

    if not inventory["conformance"]["scenarios"]:
        lines.append("- (none)")

    lines.extend([
        "",
        "### Assertions",
        ""
    ])

    for assertion in inventory["conformance"]["assertions"]:
        lines.append(f"- [{assertion['name']}]({assertion['path']})")

    if not inventory["conformance"]["assertions"]:
        lines.append("- (none)")

    lines.extend([
        "",
        "---",
        "",
        "## Requirements Index",
        "",
        "| ID | Title |",
        "|----|-------|"
    ])

    for req in inventory["requirements"]:
        lines.append(f"| {req['id']} | {req['title']} |")

    if not inventory["requirements"]:
        lines.append("| (none) | |")

    lines.extend([
        "",
        "---",
        "",
        "## Documentation Files",
        ""
    ])

    for doc in inventory["docs"]:
        lines.append(f"- [{doc['name']}]({doc['path']})")

    if not inventory["docs"]:
        lines.append("- (none)")

    lines.append("")
    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate workspace inventory")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    parser.add_argument("--md", action="store_true", help="Output Markdown only")
    parser.add_argument("--stdout", action="store_true", help="Print to stdout instead of writing files")
    args = parser.parse_args()

    inventory = generate_inventory()

    if args.stdout:
        if args.json:
            print(json.dumps(inventory, indent=2))
        elif args.md:
            print(generate_markdown(inventory))
        else:
            print(json.dumps(inventory, indent=2))
            print("\n---\n")
            print(generate_markdown(inventory))
        return 0

    TRACEABILITY_DIR.mkdir(parents=True, exist_ok=True)

    if not args.md:
        json_path = TRACEABILITY_DIR / "inventory.json"
        with open(json_path, "w") as f:
            json.dump(inventory, f, indent=2)
        print(f"Written: {json_path}")

    if not args.json:
        md_path = TRACEABILITY_DIR / "inventory.md"
        with open(md_path, "w") as f:
            f.write(generate_markdown(inventory))
        print(f"Written: {md_path}")

    print()
    print("Inventory Summary:")
    print(f"  Mapping: {inventory['summary']['mapping_projects']} projects, {inventory['summary']['mapping_documents']} documents")
    print(f"  Specs: {inventory['summary']['specs_total']} total")
    print(f"  Conformance: {inventory['summary']['scenarios']} scenarios, {inventory['summary']['assertions']} assertions")
    print(f"  Requirements: {inventory['summary']['requirements']} extracted")

    return 0


if __name__ == "__main__":
    sys.exit(main())
