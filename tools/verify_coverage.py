#!/usr/bin/env python3
"""
Coverage Analyzer - cross-references requirements with mappings, specs, and assertions.

Extracts requirement IDs (REQ-XXX, GAP-XXX) from:
- traceability/requirements.md
- traceability/gaps.md

Then scans for references in:
- mapping/**/*.md
- specs/**/*.yaml
- conformance/assertions/**/*.yaml
- docs/**/*.md

Usage:
    python tools/verify_coverage.py           # Full coverage analysis
    python tools/verify_coverage.py --json    # Output JSON only
    python tools/verify_coverage.py --gaps    # Focus on gap coverage

Outputs:
    traceability/coverage-analysis.json  - Machine-readable coverage matrix
    traceability/coverage-analysis.md    - Human-readable coverage report
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


def extract_requirements(filepath):
    """Extract requirement definitions from requirements.md."""
    requirements = {}
    
    if not filepath.exists():
        return requirements
    
    content = filepath.read_text(errors="ignore")
    
    current_req = None
    current_statement = []
    
    for line in content.split('\n'):
        req_header = re.match(r'^###\s+(REQ-\d{3}):', line)
        if req_header:
            if current_req and current_statement:
                requirements[current_req]["statement"] = ' '.join(current_statement).strip()
            current_req = req_header.group(1)
            title = line.split(':', 1)[1].strip() if ':' in line else ""
            requirements[current_req] = {
                "id": current_req,
                "title": title,
                "statement": "",
                "line": content[:content.find(line)].count('\n') + 1
            }
            current_statement = []
            continue
        
        if current_req:
            if line.startswith('**Statement**:'):
                current_statement = [line.replace('**Statement**:', '').strip()]
            elif line.startswith('**') or line.startswith('###') or line.startswith('---'):
                if current_statement:
                    requirements[current_req]["statement"] = ' '.join(current_statement).strip()
                current_statement = []
                if line.startswith('###'):
                    current_req = None
            elif current_statement:
                current_statement.append(line.strip())
    
    if current_req and current_statement:
        requirements[current_req]["statement"] = ' '.join(current_statement).strip()
    
    return requirements


def extract_gaps(filepath):
    """Extract gap definitions from gaps.md."""
    gaps = {}
    
    if not filepath.exists():
        return gaps
    
    content = filepath.read_text(errors="ignore")
    
    for match in re.finditer(r'^###\s+(GAP-[A-Z]+-\d{3}):\s*(.+)$', content, re.MULTILINE):
        gap_id = match.group(1)
        title = match.group(2).strip()
        line = content[:match.start()].count('\n') + 1
        gaps[gap_id] = {
            "id": gap_id,
            "title": title,
            "line": line
        }
    
    return gaps


def find_references(directory, patterns, file_globs=("*.md", "*.yaml", "*.yml")):
    """Find all references to requirements/gaps in a directory."""
    refs = defaultdict(list)
    
    if not directory.exists():
        return refs
    
    for glob in file_globs:
        for filepath in directory.rglob(glob):
            if filepath.name.startswith('_'):
                continue
            if '.git' in str(filepath):
                continue
            
            try:
                content = filepath.read_text(errors="ignore")
                rel_path = str(filepath.relative_to(WORKSPACE_ROOT))
                
                for pattern in patterns:
                    for match in pattern.finditer(content):
                        ref_id = match.group(1)
                        line = content[:match.start()].count('\n') + 1
                        refs[ref_id].append({
                            "file": rel_path,
                            "line": line,
                            "context": content[max(0, match.start()-40):match.end()+40].strip()
                        })
            
            except Exception as e:
                print(f"Warning: Could not read {filepath}: {e}")
    
    return refs


def analyze_coverage(requirements, gaps, mapping_refs, spec_refs, assertion_refs, doc_refs):
    """Analyze coverage of requirements and gaps."""
    coverage = {
        "requirements": {},
        "gaps": {}
    }
    
    for req_id, req_info in requirements.items():
        coverage["requirements"][req_id] = {
            **req_info,
            "mapping_refs": mapping_refs.get(req_id, []),
            "spec_refs": spec_refs.get(req_id, []),
            "assertion_refs": assertion_refs.get(req_id, []),
            "doc_refs": doc_refs.get(req_id, []),
            "total_refs": (
                len(mapping_refs.get(req_id, [])) +
                len(spec_refs.get(req_id, [])) +
                len(assertion_refs.get(req_id, [])) +
                len(doc_refs.get(req_id, []))
            ),
            "has_mapping": len(mapping_refs.get(req_id, [])) > 0,
            "has_assertion": len(assertion_refs.get(req_id, [])) > 0,
            "coverage_level": "none"
        }
        
        entry = coverage["requirements"][req_id]
        if entry["has_mapping"] and entry["has_assertion"]:
            entry["coverage_level"] = "full"
        elif entry["has_mapping"] or entry["has_assertion"]:
            entry["coverage_level"] = "partial"
        elif entry["total_refs"] > 0:
            entry["coverage_level"] = "documented"
    
    for gap_id, gap_info in gaps.items():
        coverage["gaps"][gap_id] = {
            **gap_info,
            "mapping_refs": mapping_refs.get(gap_id, []),
            "spec_refs": spec_refs.get(gap_id, []),
            "assertion_refs": assertion_refs.get(gap_id, []),
            "doc_refs": doc_refs.get(gap_id, []),
            "total_refs": (
                len(mapping_refs.get(gap_id, [])) +
                len(spec_refs.get(gap_id, [])) +
                len(assertion_refs.get(gap_id, [])) +
                len(doc_refs.get(gap_id, []))
            ),
            "addressed_in_spec": len(spec_refs.get(gap_id, [])) > 0,
            "has_assertion": len(assertion_refs.get(gap_id, [])) > 0
        }
    
    return coverage


def generate_report(coverage):
    """Generate summary report."""
    req_stats = {
        "total": len(coverage["requirements"]),
        "full": 0,
        "partial": 0,
        "documented": 0,
        "none": 0
    }
    
    for req in coverage["requirements"].values():
        req_stats[req["coverage_level"]] += 1
    
    gap_stats = {
        "total": len(coverage["gaps"]),
        "addressed": sum(1 for g in coverage["gaps"].values() if g["addressed_in_spec"]),
        "with_assertions": sum(1 for g in coverage["gaps"].values() if g["has_assertion"]),
        "orphaned": sum(1 for g in coverage["gaps"].values() if g["total_refs"] == 0)
    }
    
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "requirements": req_stats,
            "gaps": gap_stats
        },
        "requirements": coverage["requirements"],
        "gaps": coverage["gaps"],
        "uncovered_requirements": [
            req_id for req_id, req in coverage["requirements"].items()
            if req["coverage_level"] == "none"
        ],
        "orphaned_gaps": [
            gap_id for gap_id, gap in coverage["gaps"].items()
            if gap["total_refs"] == 0
        ]
    }


def generate_markdown(report):
    """Generate human-readable markdown report."""
    lines = [
        "# Coverage Analysis Report",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        "### Requirements Coverage",
        "",
        "| Level | Count | Description |",
        "|-------|-------|-------------|",
        f"| Full | {report['summary']['requirements']['full']} | Has mapping AND assertion |",
        f"| Partial | {report['summary']['requirements']['partial']} | Has mapping OR assertion |",
        f"| Documented | {report['summary']['requirements']['documented']} | Referenced but no mapping/assertion |",
        f"| None | {report['summary']['requirements']['none']} | No references found |",
        f"| **Total** | {report['summary']['requirements']['total']} | |",
        "",
        "### Gaps Coverage",
        "",
        "| Metric | Count |",
        "|--------|-------|",
        f"| Total Gaps | {report['summary']['gaps']['total']} |",
        f"| Addressed in Spec | {report['summary']['gaps']['addressed']} |",
        f"| With Assertions | {report['summary']['gaps']['with_assertions']} |",
        f"| Orphaned | {report['summary']['gaps']['orphaned']} |",
        "",
    ]
    
    if report["uncovered_requirements"]:
        lines.extend([
            "## Uncovered Requirements",
            "",
            "These requirements have no references in mappings, specs, or assertions:",
            ""
        ])
        for req_id in report["uncovered_requirements"]:
            req = report["requirements"][req_id]
            title = req.get("title", "")
            lines.append(f"- **{req_id}**: {title}")
        lines.append("")
    
    if report["orphaned_gaps"]:
        lines.extend([
            "## Orphaned Gaps",
            "",
            "These gaps are defined but have no references elsewhere:",
            ""
        ])
        for gap_id in report["orphaned_gaps"]:
            gap = report["gaps"][gap_id]
            title = gap.get("title", "")
            lines.append(f"- **{gap_id}**: {title}")
        lines.append("")
    
    lines.extend([
        "## Requirements Detail",
        "",
        "| ID | Title | Mappings | Assertions | Level |",
        "|----|-------|----------|------------|-------|"
    ])
    
    for req_id in sorted(report["requirements"].keys()):
        req = report["requirements"][req_id]
        title = req.get("title", "")[:40]
        mappings = len(req.get("mapping_refs", []))
        assertions = len(req.get("assertion_refs", []))
        level = req.get("coverage_level", "none")
        level_icon = {"full": "✅", "partial": "⚠️", "documented": "📄", "none": "❌"}.get(level, "")
        lines.append(f"| {req_id} | {title} | {mappings} | {assertions} | {level_icon} {level} |")
    
    lines.append("")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Analyze coverage of requirements and gaps")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    parser.add_argument("--gaps", action="store_true", help="Focus on gap coverage")
    parser.add_argument("--no-write", action="store_true", help="Don't write output files")
    args = parser.parse_args()
    
    print("Extracting requirements...")
    requirements = extract_requirements(TRACEABILITY_DIR / "requirements.md")
    print(f"  Found {len(requirements)} requirements")
    
    print("Extracting gaps...")
    gaps = extract_gaps(TRACEABILITY_DIR / "gaps.md")
    print(f"  Found {len(gaps)} gaps")
    
    patterns = [REQ_PATTERN, GAP_PATTERN]
    
    print("Scanning mappings...")
    mapping_refs = find_references(MAPPING_DIR, patterns)
    
    print("Scanning specs...")
    spec_refs = find_references(SPECS_DIR, patterns)
    
    print("Scanning assertions...")
    assertion_refs = find_references(CONFORMANCE_DIR, patterns)
    
    print("Scanning docs...")
    doc_refs = find_references(DOCS_DIR, patterns)
    
    print("Analyzing coverage...")
    coverage = analyze_coverage(
        requirements, gaps,
        mapping_refs, spec_refs, assertion_refs, doc_refs
    )
    
    report = generate_report(coverage)
    
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"\nCoverage Summary:")
        print(f"  Requirements: {report['summary']['requirements']['total']}")
        print(f"    - Full coverage: {report['summary']['requirements']['full']}")
        print(f"    - Partial: {report['summary']['requirements']['partial']}")
        print(f"    - Documented only: {report['summary']['requirements']['documented']}")
        print(f"    - No coverage: {report['summary']['requirements']['none']}")
        print(f"  Gaps: {report['summary']['gaps']['total']}")
        print(f"    - Addressed in spec: {report['summary']['gaps']['addressed']}")
        print(f"    - With assertions: {report['summary']['gaps']['with_assertions']}")
        print(f"    - Orphaned: {report['summary']['gaps']['orphaned']}")
    
    if not args.no_write:
        TRACEABILITY_DIR.mkdir(parents=True, exist_ok=True)
        
        json_path = TRACEABILITY_DIR / "coverage-analysis.json"
        with open(json_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nWrote: {json_path}")
        
        md_path = TRACEABILITY_DIR / "coverage-analysis.md"
        with open(md_path, "w") as f:
            f.write(generate_markdown(report))
        print(f"Wrote: {md_path}")
    
    uncovered = len(report["uncovered_requirements"])
    return 1 if uncovered > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
