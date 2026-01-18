#!/usr/bin/env python3
"""
Traceability Matrix Generator - creates comprehensive traceability reports.

Generates traceability matrices linking:
- Requirements → Specs → Tests → Documentation
- Gaps → Documentation → Remediation
- API Endpoints → Implementations → Tests
- Architecture Elements → Code References

Usage:
    # Generate full traceability matrix
    python tools/gen_traceability.py

    # Generate specific matrix type
    python tools/gen_traceability.py --type requirements

    # JSON output
    python tools/gen_traceability.py --json

    # Include code references
    python tools/gen_traceability.py --include-code-refs

For AI agents:
    # Get traceability for a requirement
    python tools/gen_traceability.py --type requirements --json | jq '.requirements["REQ-001"]'
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).parent.parent
TRACEABILITY_DIR = WORKSPACE_ROOT / "traceability"
MAPPING_DIR = WORKSPACE_ROOT / "mapping"
SPECS_DIR = WORKSPACE_ROOT / "specs"
CONFORMANCE_DIR = WORKSPACE_ROOT / "conformance"
DOCS_DIR = WORKSPACE_ROOT / "docs"

REQ_PATTERN = re.compile(r'\b(REQ-\d{3})\b')
GAP_PATTERN = re.compile(r'\b(GAP-[A-Z]+-\d{3})\b')
CODE_REF_PATTERN = re.compile(r'`([a-zA-Z0-9_-]+:[^`]+)`')


def extract_requirements():
    """Extract all requirements with their metadata."""
    requirements_file = TRACEABILITY_DIR / "requirements.md"
    requirements = {}
    
    if not requirements_file.exists():
        return requirements
    
    content = requirements_file.read_text(errors="ignore")
    current_req = None
    current_data = {}
    in_statement = False
    statement_lines = []
    
    for line in content.split('\n'):
        req_match = re.match(r'^###\s+(REQ-\d{3}):\s*(.+)$', line)
        if req_match:
            # Save previous requirement
            if current_req and statement_lines:
                current_data["statement"] = ' '.join(statement_lines).strip()
                requirements[current_req] = current_data
            
            # Start new requirement
            current_req = req_match.group(1)
            current_data = {
                "id": current_req,
                "title": req_match.group(2).strip(),
                "statement": "",
                "rationale": "",
                "scenarios": [],
                "verification": "",
                "mapped_in": [],
                "tested_by": [],
                "referenced_in": []
            }
            statement_lines = []
            in_statement = False
            continue
        
        if current_req:
            if line.startswith("**Statement**:"):
                in_statement = True
                statement_lines = [line.replace("**Statement**:", "").strip()]
            elif line.startswith("**Rationale**:"):
                in_statement = False
                if statement_lines:
                    current_data["statement"] = ' '.join(statement_lines).strip()
                    statement_lines = []
                current_data["rationale"] = line.replace("**Rationale**:", "").strip()
            elif line.startswith("**Scenarios**:"):
                in_statement = False
                scenarios_text = line.replace("**Scenarios**:", "").strip()
                current_data["scenarios"] = [s.strip() for s in scenarios_text.split(',') if s.strip()]
            elif line.startswith("**Verification**:"):
                in_statement = False
                current_data["verification"] = line.replace("**Verification**:", "").strip()
            elif in_statement and line.strip() and not line.startswith("**"):
                statement_lines.append(line.strip())
            elif line.startswith("###") or line.startswith("---"):
                in_statement = False
    
    # Save last requirement
    if current_req:
        if statement_lines:
            current_data["statement"] = ' '.join(statement_lines).strip()
        requirements[current_req] = current_data
    
    return requirements


def extract_gaps():
    """Extract all gaps with their metadata."""
    gaps_file = TRACEABILITY_DIR / "gaps.md"
    gaps = {}
    
    if not gaps_file.exists():
        return gaps
    
    content = gaps_file.read_text(errors="ignore")
    
    for match in re.finditer(r'^###\s+(GAP-[A-Z]+-\d{3}):\s*(.+)$', content, re.MULTILINE):
        gap_id = match.group(1)
        title = match.group(2).strip()
        gaps[gap_id] = {
            "id": gap_id,
            "title": title,
            "category": gap_id.split('-')[1],
            "documented_in": [],
            "related_requirements": []
        }
    
    return gaps


def scan_mapping_documents(requirements, gaps):
    """Scan mapping documents for requirement and gap references."""
    if not MAPPING_DIR.exists():
        return
    
    for md_file in MAPPING_DIR.rglob("*.md"):
        content = md_file.read_text(errors="ignore")
        rel_path = str(md_file.relative_to(WORKSPACE_ROOT))
        
        # Find requirements referenced
        for req_id in REQ_PATTERN.findall(content):
            if req_id in requirements:
                requirements[req_id]["mapped_in"].append(rel_path)
        
        # Find gaps referenced
        for gap_id in GAP_PATTERN.findall(content):
            if gap_id in gaps:
                gaps[gap_id]["documented_in"].append(rel_path)


def scan_test_scenarios(requirements, gaps):
    """Scan conformance test scenarios for coverage."""
    assertions_dir = CONFORMANCE_DIR / "assertions"
    
    if not assertions_dir.exists():
        return
    
    for yaml_file in assertions_dir.glob("*.yaml"):
        if yaml_file.name == "_template.yaml":
            continue
        
        content = yaml_file.read_text(errors="ignore")
        rel_path = str(yaml_file.relative_to(WORKSPACE_ROOT))
        
        # Extract scenario name
        scenario_match = re.search(r'^scenario:\s*(.+)$', content, re.MULTILINE)
        scenario = scenario_match.group(1).strip() if scenario_match else yaml_file.stem
        
        # Find requirements tested
        for req_id in REQ_PATTERN.findall(content):
            if req_id in requirements:
                requirements[req_id]["tested_by"].append({
                    "scenario": scenario,
                    "file": rel_path
                })
        
        # Find gaps addressed
        for gap_id in GAP_PATTERN.findall(content):
            if gap_id in gaps:
                gaps[gap_id]["related_requirements"].extend(REQ_PATTERN.findall(content))


def scan_documentation(requirements, gaps):
    """Scan general documentation for references."""
    if not DOCS_DIR.exists():
        return
    
    for md_file in DOCS_DIR.rglob("*.md"):
        content = md_file.read_text(errors="ignore")
        rel_path = str(md_file.relative_to(WORKSPACE_ROOT))
        
        # Find requirements referenced
        for req_id in REQ_PATTERN.findall(content):
            if req_id in requirements:
                requirements[req_id]["referenced_in"].append(rel_path)
        
        # Find gaps referenced
        for gap_id in GAP_PATTERN.findall(content):
            if gap_id in gaps:
                gaps[gap_id]["documented_in"].append(rel_path)


def extract_api_endpoints():
    """Extract API endpoints from OpenAPI specs."""
    endpoints = {}
    openapi_dir = SPECS_DIR / "openapi"
    
    if not openapi_dir.exists():
        return endpoints
    
    try:
        import yaml
        has_yaml = True
    except ImportError:
        has_yaml = False
        return endpoints
    
    for yaml_file in openapi_dir.glob("*.yaml"):
        try:
            with open(yaml_file) as f:
                spec = yaml.safe_load(f)
            
            if not isinstance(spec, dict) or "paths" not in spec:
                continue
            
            spec_name = yaml_file.stem
            
            for path, methods in spec["paths"].items():
                if not isinstance(methods, dict):
                    continue
                
                for method, details in methods.items():
                    if method.lower() in ["get", "post", "put", "delete", "patch"]:
                        endpoint_id = f"{method.upper()} {path}"
                        endpoints[endpoint_id] = {
                            "method": method.upper(),
                            "path": path,
                            "spec": spec_name,
                            "summary": details.get("summary", ""),
                            "operationId": details.get("operationId", ""),
                            "tested_by": [],
                            "implemented_in": []
                        }
        except Exception:
            continue
    
    return endpoints


def generate_requirements_matrix(requirements):
    """Generate requirements traceability matrix."""
    matrix = {
        "total": len(requirements),
        "mapped": sum(1 for r in requirements.values() if r["mapped_in"]),
        "tested": sum(1 for r in requirements.values() if r["tested_by"]),
        "documented": sum(1 for r in requirements.values() if r["referenced_in"]),
        "requirements": requirements
    }
    
    # Calculate coverage stats
    matrix["coverage"] = {
        "mapping": round(matrix["mapped"] / matrix["total"] * 100, 1) if matrix["total"] > 0 else 0,
        "testing": round(matrix["tested"] / matrix["total"] * 100, 1) if matrix["total"] > 0 else 0,
        "documentation": round(matrix["documented"] / matrix["total"] * 100, 1) if matrix["total"] > 0 else 0
    }
    
    # Identify gaps
    matrix["gaps"] = {
        "unmapped": [r["id"] for r in requirements.values() if not r["mapped_in"]],
        "untested": [r["id"] for r in requirements.values() if not r["tested_by"]],
        "undocumented": [r["id"] for r in requirements.values() if not r["referenced_in"]]
    }
    
    return matrix


def generate_gaps_matrix(gaps):
    """Generate gaps traceability matrix."""
    matrix = {
        "total": len(gaps),
        "documented": sum(1 for g in gaps.values() if g["documented_in"]),
        "gaps": gaps
    }
    
    # Group by category
    categories = defaultdict(list)
    for gap in gaps.values():
        categories[gap["category"]].append(gap["id"])
    
    matrix["by_category"] = dict(categories)
    
    return matrix


def generate_markdown_report(matrix_type, data):
    """Generate markdown report for a matrix."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    lines = [
        f"# {matrix_type.title()} Traceability Matrix",
        "",
        f"Generated: {timestamp}",
        ""
    ]
    
    if matrix_type == "requirements":
        lines.extend([
            "## Summary",
            "",
            f"- Total Requirements: {data['total']}",
            f"- Mapped in Documentation: {data['mapped']} ({data['coverage']['mapping']}%)",
            f"- Covered by Tests: {data['tested']} ({data['coverage']['testing']}%)",
            f"- Referenced in Docs: {data['documented']} ({data['coverage']['documentation']}%)",
            "",
            "## Coverage Gaps",
            "",
            f"### Unmapped ({len(data['gaps']['unmapped'])} requirements)",
            ""
        ])
        
        for req_id in data['gaps']['unmapped']:
            req = data['requirements'][req_id]
            lines.append(f"- {req_id}: {req['title']}")
        
        lines.extend([
            "",
            f"### Untested ({len(data['gaps']['untested'])} requirements)",
            ""
        ])
        
        for req_id in data['gaps']['untested']:
            req = data['requirements'][req_id]
            lines.append(f"- {req_id}: {req['title']}")
    
    elif matrix_type == "gaps":
        lines.extend([
            "## Summary",
            "",
            f"- Total Gaps: {data['total']}",
            f"- Documented: {data['documented']}",
            "",
            "## By Category",
            ""
        ])
        
        for category, gap_ids in sorted(data['by_category'].items()):
            lines.append(f"### {category} ({len(gap_ids)} gaps)")
            lines.append("")
            for gap_id in gap_ids:
                gap = data['gaps'][gap_id]
                lines.append(f"- {gap_id}: {gap['title']}")
            lines.append("")
    
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate traceability matrices")
    parser.add_argument("--type", choices=["requirements", "gaps", "api", "all"], 
                       default="all", help="Type of matrix to generate")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--include-code-refs", action="store_true", 
                       help="Include code reference analysis (slower)")
    parser.add_argument("--output-dir", default=str(TRACEABILITY_DIR),
                       help="Output directory for reports")
    
    args = parser.parse_args()
    
    # Extract data
    requirements = extract_requirements()
    gaps = extract_gaps()
    
    # Scan for references
    scan_mapping_documents(requirements, gaps)
    scan_test_scenarios(requirements, gaps)
    scan_documentation(requirements, gaps)
    
    # Generate matrices
    output = {}
    
    if args.type in ["requirements", "all"]:
        matrix = generate_requirements_matrix(requirements)
        output["requirements"] = matrix
        
        if not args.json:
            report = generate_markdown_report("requirements", matrix)
            output_file = Path(args.output_dir) / "traceability-requirements.md"
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(report)
            print(f"Generated: {output_file}")
    
    if args.type in ["gaps", "all"]:
        matrix = generate_gaps_matrix(gaps)
        output["gaps"] = matrix
        
        if not args.json:
            report = generate_markdown_report("gaps", matrix)
            output_file = Path(args.output_dir) / "traceability-gaps.md"
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(report)
            print(f"Generated: {output_file}")
    
    if args.type in ["api", "all"]:
        endpoints = extract_api_endpoints()
        output["api_endpoints"] = {
            "total": len(endpoints),
            "endpoints": endpoints
        }
    
    # Output JSON
    if args.json:
        output["timestamp"] = datetime.now(timezone.utc).isoformat()
        print(json.dumps(output, indent=2))
    
    # Save JSON files
    if not args.json and args.type == "all":
        json_file = Path(args.output_dir) / "traceability-full.json"
        output["timestamp"] = datetime.now(timezone.utc).isoformat()
        json_file.write_text(json.dumps(output, indent=2))
        print(f"Generated: {json_file}")


if __name__ == "__main__":
    main()
