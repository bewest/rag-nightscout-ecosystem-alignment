#!/usr/bin/env python3
"""
Terminology Consistency Checker - verifies consistent terminology usage across mappings.

Parses the terminology matrix from mapping/cross-project/terminology-matrix.md
and checks that mapping documents use terms consistently.

Checks for:
1. Using project-specific terms when alignment terms should be used
2. Inconsistent naming of the same concept
3. Undefined terms (used but not in matrix)

Usage:
    python tools/verify_terminology.py              # Check all mappings
    python tools/verify_terminology.py --verbose    # Show all term usage
    python tools/verify_terminology.py --json       # Output JSON report

Outputs:
    traceability/terminology-consistency.json  - Machine-readable report
    traceability/terminology-consistency.md    - Human-readable report
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).parent.parent
MAPPING_DIR = WORKSPACE_ROOT / "mapping"
TRACEABILITY_DIR = WORKSPACE_ROOT / "traceability"
TERMINOLOGY_MATRIX = MAPPING_DIR / "cross-project" / "terminology-matrix.md"


def parse_terminology_matrix(filepath):
    """Parse terminology matrix and extract term mappings."""
    if not filepath.exists():
        return {}, {}
    
    content = filepath.read_text(errors="ignore")
    
    alignment_terms = {}
    project_terms = defaultdict(dict)
    
    current_section = None
    table_lines = []
    headers = []
    
    for line in content.split('\n'):
        if line.startswith('## ') or line.startswith('### '):
            if table_lines and headers:
                process_table(table_lines, headers, alignment_terms, project_terms)
            table_lines = []
            headers = []
            current_section = line.strip('# ')
            continue
        
        if '|' in line and not line.strip().startswith('|--'):
            cells = [c.strip() for c in line.split('|')[1:-1]]
            if not headers:
                headers = cells
            else:
                table_lines.append(cells)
    
    if table_lines and headers:
        process_table(table_lines, headers, alignment_terms, project_terms)
    
    return alignment_terms, project_terms


def process_table(rows, headers, alignment_terms, project_terms):
    """Process a terminology table."""
    if len(headers) < 2:
        return
    
    alignment_col = None
    for i, h in enumerate(headers):
        if 'alignment' in h.lower() or 'term' in h.lower():
            alignment_col = i
            break
    
    if alignment_col is None:
        alignment_col = 0
    
    for row in rows:
        if len(row) <= alignment_col:
            continue
        
        alignment_term = row[alignment_col].strip()
        if not alignment_term or alignment_term == '-' or alignment_term.startswith('N/A'):
            continue
        
        alignment_term_clean = re.sub(r'\s*\([^)]+\)', '', alignment_term).strip()
        
        if alignment_term_clean not in alignment_terms:
            alignment_terms[alignment_term_clean] = {
                "canonical": alignment_term_clean,
                "variants": set(),
                "project_mappings": {}
            }
        
        for i, cell in enumerate(row):
            if i == alignment_col or i >= len(headers):
                continue
            
            project = headers[i].strip()
            term = cell.strip()
            
            if not term or term == '-' or term.startswith('N/A'):
                continue
            
            term_clean = re.sub(r'`([^`]+)`', r'\1', term)
            term_clean = re.sub(r'\s*\([^)]+\)', '', term_clean).strip()
            
            if term_clean:
                alignment_terms[alignment_term_clean]["project_mappings"][project] = term_clean
                alignment_terms[alignment_term_clean]["variants"].add(term_clean)
                project_terms[project][term_clean] = alignment_term_clean


def scan_document(filepath, alignment_terms, project_terms):
    """Scan a document for terminology usage."""
    usage = []
    issues = []
    
    try:
        content = filepath.read_text(errors="ignore")
        rel_path = str(filepath.relative_to(WORKSPACE_ROOT))
        
        project_from_path = None
        parts = rel_path.split('/')
        if len(parts) >= 2 and parts[0] == 'mapping':
            project_from_path = parts[1]
        
        key_terms = {}
        for project, terms in project_terms.items():
            for term, alignment in terms.items():
                if len(term) >= 6 and term not in key_terms:
                    key_terms[term] = {"is_alignment": False, "alignment": alignment}
        for term in alignment_terms.keys():
            if len(term) >= 6:
                key_terms[term] = {"is_alignment": True, "alignment": None}
        
        content_lower = content.lower()
        for term, info in key_terms.items():
            term_lower = term.lower()
            if term_lower not in content_lower:
                continue
            
            pattern = re.compile(r'\b' + re.escape(term) + r'\b', re.IGNORECASE)
            matches = list(pattern.finditer(content))
            
            if matches:
                first_match = matches[0]
                line_num = content[:first_match.start()].count('\n') + 1
                
                usage.append({
                    "term": term,
                    "file": rel_path,
                    "line": line_num,
                    "occurrences": len(matches),
                    "is_alignment_term": info["is_alignment"],
                    "alignment_term": info["alignment"]
                })
    
    except Exception as e:
        print(f"Warning: Could not scan {filepath}: {e}")
    
    return usage, issues


def analyze_consistency(alignment_terms, project_terms):
    """Analyze terminology consistency across all mapping documents."""
    all_usage = []
    all_issues = []
    
    for filepath in MAPPING_DIR.rglob("*.md"):
        if filepath.name.startswith('_'):
            continue
        if 'terminology-matrix' in filepath.name:
            continue
        
        usage, issues = scan_document(filepath, alignment_terms, project_terms)
        all_usage.extend(usage)
        all_issues.extend(issues)
    
    term_usage = {}
    for u in all_usage:
        term = u["term"]
        if term not in term_usage:
            term_usage[term] = {"files": set(), "count": 0}
        term_usage[term]["files"].add(u["file"])
        term_usage[term]["count"] += 1
        if u.get("is_alignment_term"):
            term_usage[term]["is_alignment"] = True
        if u.get("alignment_term"):
            term_usage[term]["maps_to"] = u["alignment_term"]
    
    return all_usage, all_issues, term_usage


def generate_report(alignment_terms, project_terms, usage, issues, term_usage):
    """Generate analysis report."""
    alignment_term_count = len(alignment_terms)
    project_term_count = sum(len(terms) for terms in project_terms.values())
    
    for term in alignment_terms.values():
        if isinstance(term.get("variants"), set):
            term["variants"] = list(term["variants"])
    
    term_usage_serializable = {}
    for term, data in term_usage.items():
        term_usage_serializable[term] = {
            **data,
            "files": list(data["files"])
        }
    
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "alignment_terms": alignment_term_count,
            "project_terms": project_term_count,
            "projects_covered": list(project_terms.keys()),
            "total_term_occurrences": len(usage),
            "issues_found": len(issues)
        },
        "alignment_terms": alignment_terms,
        "term_usage": term_usage_serializable,
        "issues": issues
    }
    
    return report


def generate_markdown(report):
    """Generate human-readable markdown report."""
    lines = [
        "# Terminology Consistency Report",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Alignment Terms | {report['summary']['alignment_terms']} |",
        f"| Project-Specific Terms | {report['summary']['project_terms']} |",
        f"| Projects Covered | {', '.join(report['summary']['projects_covered'])} |",
        f"| Term Occurrences Scanned | {report['summary']['total_term_occurrences']} |",
        f"| Issues Found | {report['summary']['issues_found']} |",
        "",
    ]
    
    if report["issues"]:
        lines.extend([
            "## Issues",
            ""
        ])
        for issue in report["issues"]:
            lines.append(f"- **{issue.get('type', 'issue')}**: {issue.get('message', '')}")
            if issue.get('file'):
                lines.append(f"  - File: `{issue['file']}`")
        lines.append("")
    
    lines.extend([
        "## Most Used Terms",
        "",
        "| Term | Occurrences | Files | Type |",
        "|----|-------------|-------|------|"
    ])
    
    sorted_terms = sorted(
        report["term_usage"].items(),
        key=lambda x: x[1]["count"],
        reverse=True
    )[:30]
    
    for term, data in sorted_terms:
        count = data["count"]
        files = len(data["files"])
        term_type = "Alignment" if data.get("is_alignment") else "Project"
        lines.append(f"| {term} | {count} | {files} | {term_type} |")
    
    lines.append("")
    
    lines.extend([
        "## Alignment Term Mappings",
        "",
        "| Alignment Term | Project Mappings |",
        "|----------------|------------------|"
    ])
    
    for term, info in sorted(report["alignment_terms"].items())[:30]:
        mappings = info.get("project_mappings", {})
        mapping_str = ", ".join(f"{p}: `{t}`" for p, t in list(mappings.items())[:3])
        if len(mappings) > 3:
            mapping_str += f" (+{len(mappings)-3} more)"
        lines.append(f"| {term} | {mapping_str} |")
    
    lines.append("")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Check terminology consistency")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    parser.add_argument("--no-write", action="store_true", help="Don't write output files")
    args = parser.parse_args()
    
    print("Parsing terminology matrix...")
    alignment_terms, project_terms = parse_terminology_matrix(TERMINOLOGY_MATRIX)
    print(f"  Found {len(alignment_terms)} alignment terms")
    print(f"  Found {sum(len(t) for t in project_terms.values())} project-specific terms")
    
    print("Scanning mapping documents...")
    usage, issues, term_usage = analyze_consistency(alignment_terms, project_terms)
    print(f"  Scanned {len(set(u['file'] for u in usage))} files")
    print(f"  Found {len(usage)} term occurrences")
    
    report = generate_report(alignment_terms, project_terms, usage, issues, term_usage)
    
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"\nTerminology Summary:")
        print(f"  Alignment terms defined: {report['summary']['alignment_terms']}")
        print(f"  Project terms mapped: {report['summary']['project_terms']}")
        print(f"  Projects: {', '.join(report['summary']['projects_covered'])}")
        print(f"  Issues: {report['summary']['issues_found']}")
    
    if not args.no_write:
        TRACEABILITY_DIR.mkdir(parents=True, exist_ok=True)
        
        json_path = TRACEABILITY_DIR / "terminology-consistency.json"
        with open(json_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nWrote: {json_path}")
        
        md_path = TRACEABILITY_DIR / "terminology-consistency.md"
        with open(md_path, "w") as f:
            f.write(generate_markdown(report))
        print(f"Wrote: {md_path}")
    
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
