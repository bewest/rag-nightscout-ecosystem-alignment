#!/usr/bin/env python3
"""
Spec Capture - Extracts and verifies specifications from mapping documents.

Captures implicit requirements from source analysis and verifies they match source code.
Integrates with the traceability system to ensure specs stay aligned with implementations.

Usage:
    # Extract specs from a mapping document
    python tools/spec_capture.py extract mapping/loop-sync.md

    # Verify a specific requirement against source
    python tools/spec_capture.py verify REQ-001

    # Scan all mappings for implicit requirements
    python tools/spec_capture.py scan

    # Check spec coverage
    python tools/spec_capture.py coverage

    # JSON output for agents
    python tools/spec_capture.py scan --json

For AI agents:
    python tools/spec_capture.py extract mapping/x.md --json | jq '.specs[]'
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
DOCS_DIR = WORKSPACE_ROOT / "docs"
TRACEABILITY_DIR = WORKSPACE_ROOT / "traceability"
EXTERNALS_DIR = WORKSPACE_ROOT / "externals"
LOCKFILE = WORKSPACE_ROOT / "workspace.lock.json"

REQ_PATTERN = re.compile(r'\b(REQ-\d{3})\b')
GAP_PATTERN = re.compile(r'\b(GAP-[A-Z]+-\d{3})\b')
CODE_REF_PATTERN = re.compile(r'`([a-zA-Z][a-zA-Z0-9_-]{0,15}):([a-zA-Z0-9_./-]+)(?:#(.+))?`')

SPEC_INDICATORS = [
    (r'\b(must|shall|should|will)\s+', "requirement", 0.7),
    (r'\b(required|mandatory|necessary)\b', "requirement", 0.6),
    (r'\b(behavior|behaves?|acts?)\s+', "behavior_spec", 0.5),
    (r'\b(format|structure|schema)\s+is\b', "format_spec", 0.6),
    (r'\b(valid|invalid|allowed|forbidden)\b', "constraint", 0.5),
    (r'\b(range|minimum|maximum|between)\b', "constraint", 0.5),
    (r'\b(sync|synchronize|replicate)\b', "sync_spec", 0.4),
    (r'\b(authenticate|authorize|permission)\b', "auth_spec", 0.5),
]


def load_lockfile() -> dict:
    """Load workspace lock file."""
    if not LOCKFILE.exists():
        return {}
    try:
        return json.loads(LOCKFILE.read_text())
    except Exception:
        return {}


def get_repo_aliases() -> dict:
    """Get mapping of aliases to repo paths."""
    lockfile = load_lockfile()
    aliases = {}
    for repo_name, repo_info in lockfile.get("repositories", {}).items():
        alias = repo_info.get("alias", repo_name[:3].lower())
        aliases[alias] = repo_name
    return aliases


def load_existing_requirements() -> dict:
    """Load existing requirements from traceability."""
    requirements_file = TRACEABILITY_DIR / "requirements.md"
    requirements = {}
    
    if not requirements_file.exists():
        return requirements
    
    content = requirements_file.read_text(errors="ignore")
    current_req = None
    current_data = {}
    
    for line in content.split('\n'):
        req_match = re.match(r'^###\s+(REQ-\d{3}):\s*(.+)$', line)
        if req_match:
            if current_req:
                requirements[current_req] = current_data
            current_req = req_match.group(1)
            current_data = {
                "id": current_req,
                "title": req_match.group(2).strip(),
                "source_files": [],
                "verified": False
            }
        elif current_req and line.startswith("**Source**:"):
            current_data["source_files"] = [
                s.strip() for s in line.replace("**Source**:", "").strip().split(",")
            ]
    
    if current_req:
        requirements[current_req] = current_data
    
    return requirements


def extract_specs_from_content(content: str, source_file: str) -> list:
    """Extract implicit specifications from document content."""
    specs = []
    lines = content.split('\n')
    
    for line_num, line in enumerate(lines, 1):
        for pattern, spec_type, confidence in SPEC_INDICATORS:
            if re.search(pattern, line, re.IGNORECASE):
                code_refs = CODE_REF_PATTERN.findall(line)
                existing_reqs = REQ_PATTERN.findall(line)
                
                spec = {
                    "line": line_num,
                    "text": line.strip()[:200],
                    "type": spec_type,
                    "confidence": confidence,
                    "source_file": source_file,
                    "code_refs": [f"{r[0]}:{r[1]}" for r in code_refs],
                    "existing_reqs": existing_reqs,
                    "is_captured": len(existing_reqs) > 0
                }
                
                if len(code_refs) > 0:
                    spec["confidence"] += 0.2
                
                if spec["confidence"] >= 0.5:
                    specs.append(spec)
                break
    
    specs = list({s["text"]: s for s in specs}.values())
    specs.sort(key=lambda x: -x["confidence"])
    
    return specs


def extract_from_document(doc_path: Path) -> dict:
    """Extract specs from a single document."""
    relative_path = str(doc_path.relative_to(WORKSPACE_ROOT))
    
    try:
        content = doc_path.read_text(errors="ignore")
    except Exception as e:
        return {"path": relative_path, "error": str(e), "specs": []}
    
    specs = extract_specs_from_content(content, relative_path)
    
    existing_reqs = set(REQ_PATTERN.findall(content))
    existing_gaps = set(GAP_PATTERN.findall(content))
    code_refs = CODE_REF_PATTERN.findall(content)
    
    captured_count = sum(1 for s in specs if s["is_captured"])
    uncaptured_count = len(specs) - captured_count
    
    return {
        "path": relative_path,
        "specs": specs,
        "total_specs": len(specs),
        "captured_count": captured_count,
        "uncaptured_count": uncaptured_count,
        "existing_requirements": list(existing_reqs),
        "existing_gaps": list(existing_gaps),
        "code_refs_count": len(code_refs),
        "coverage": captured_count / len(specs) if specs else 1.0
    }


def scan_all_mappings() -> list:
    """Scan all mapping documents for specs."""
    results = []
    
    scan_dirs = [MAPPING_DIR, DOCS_DIR / "10-domain"]
    
    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        
        for md_file in scan_dir.rglob("*.md"):
            if md_file.name.startswith("_"):
                continue
            
            result = extract_from_document(md_file)
            results.append(result)
    
    results.sort(key=lambda x: -x.get("uncaptured_count", 0))
    
    return results


def verify_requirement(req_id: str, aliases: dict) -> dict:
    """Verify a requirement against source code."""
    requirements = load_existing_requirements()
    
    if req_id not in requirements:
        return {
            "req_id": req_id,
            "status": "not_found",
            "error": f"Requirement {req_id} not found in traceability"
        }
    
    req = requirements[req_id]
    
    verification = {
        "req_id": req_id,
        "title": req.get("title", ""),
        "source_files": req.get("source_files", []),
        "checks": [],
        "status": "unknown"
    }
    
    for source_ref in req.get("source_files", []):
        check = {"source": source_ref, "exists": False, "current": False}
        
        if ":" in source_ref:
            alias, path = source_ref.split(":", 1)
            path = path.split("#")[0]
            
            if alias in aliases:
                repo_name = aliases[alias]
                file_path = EXTERNALS_DIR / repo_name / path
                
                if file_path.exists():
                    check["exists"] = True
                    check["current"] = True
                    check["resolved_path"] = str(file_path.relative_to(WORKSPACE_ROOT))
        
        verification["checks"].append(check)
    
    all_exist = all(c["exists"] for c in verification["checks"]) if verification["checks"] else False
    all_current = all(c["current"] for c in verification["checks"]) if verification["checks"] else False
    
    if not verification["checks"]:
        verification["status"] = "no_sources"
    elif all_current:
        verification["status"] = "verified"
    elif all_exist:
        verification["status"] = "stale"
    else:
        verification["status"] = "broken"
    
    return verification


def get_coverage_summary(results: list) -> dict:
    """Generate spec coverage summary."""
    summary = {
        "total_documents": len(results),
        "total_specs": 0,
        "captured_specs": 0,
        "uncaptured_specs": 0,
        "fully_covered_docs": 0,
        "partially_covered_docs": 0,
        "uncovered_docs": 0,
        "documents_needing_attention": []
    }
    
    for result in results:
        summary["total_specs"] += result.get("total_specs", 0)
        summary["captured_specs"] += result.get("captured_count", 0)
        summary["uncaptured_specs"] += result.get("uncaptured_count", 0)
        
        coverage = result.get("coverage", 1.0)
        if coverage >= 1.0:
            summary["fully_covered_docs"] += 1
        elif coverage > 0:
            summary["partially_covered_docs"] += 1
        else:
            summary["uncovered_docs"] += 1
        
        if result.get("uncaptured_count", 0) > 2:
            summary["documents_needing_attention"].append({
                "path": result["path"],
                "uncaptured": result["uncaptured_count"],
                "coverage": coverage
            })
    
    summary["overall_coverage"] = (
        summary["captured_specs"] / summary["total_specs"]
        if summary["total_specs"] > 0 else 1.0
    )
    
    summary["documents_needing_attention"].sort(key=lambda x: -x["uncaptured"])
    
    return summary


def format_extraction(result: dict, verbose: bool) -> str:
    """Format extraction result for display."""
    output = []
    output.append(f"Document: {result['path']}")
    output.append(f"Total Specs Found: {result['total_specs']}")
    output.append(f"Captured: {result['captured_count']} | Uncaptured: {result['uncaptured_count']}")
    output.append(f"Coverage: {result['coverage']:.0%}")
    
    if result.get("existing_requirements"):
        output.append(f"Requirements: {', '.join(result['existing_requirements'])}")
    
    if result.get("existing_gaps"):
        output.append(f"Gaps: {', '.join(result['existing_gaps'])}")
    
    if verbose and result.get("specs"):
        output.append("\nSpecs Found:")
        for spec in result["specs"][:10]:
            status = "✓" if spec["is_captured"] else "○"
            output.append(f"  {status} [{spec['type']}] L{spec['line']}: {spec['text'][:80]}...")
            if spec.get("code_refs"):
                output.append(f"      Refs: {', '.join(spec['code_refs'][:3])}")
    
    return "\n".join(output)


def format_coverage(summary: dict) -> str:
    """Format coverage summary for display."""
    output = []
    output.append("=" * 70)
    output.append("SPEC COVERAGE REPORT")
    output.append("=" * 70)
    output.append(f"\nOverall Coverage: {summary['overall_coverage']:.0%}")
    output.append(f"Total Documents: {summary['total_documents']}")
    output.append(f"Total Specs: {summary['total_specs']}")
    output.append(f"  Captured: {summary['captured_specs']}")
    output.append(f"  Uncaptured: {summary['uncaptured_specs']}")
    output.append(f"\nDocument Coverage:")
    output.append(f"  Fully Covered: {summary['fully_covered_docs']}")
    output.append(f"  Partially Covered: {summary['partially_covered_docs']}")
    output.append(f"  Uncovered: {summary['uncovered_docs']}")
    
    if summary.get("documents_needing_attention"):
        output.append("\nDocuments Needing Attention:")
        for doc in summary["documents_needing_attention"][:10]:
            output.append(f"  - {doc['path']}: {doc['uncaptured']} uncaptured specs")
    
    return "\n".join(output)


def cmd_extract(args, json_output: bool) -> int:
    """Extract specs from a document."""
    if not args.file:
        print("Error: File path required", file=sys.stderr)
        return 1
    
    doc_path = WORKSPACE_ROOT / args.file
    if not doc_path.exists():
        if json_output:
            print(json.dumps({"error": f"File not found: {args.file}"}))
        else:
            print(f"Error: File not found: {args.file}", file=sys.stderr)
        return 1
    
    result = extract_from_document(doc_path)
    
    if json_output:
        print(json.dumps(result, indent=2))
    else:
        print(format_extraction(result, args.verbose))
    
    return 0


def cmd_verify(args, json_output: bool) -> int:
    """Verify a requirement."""
    if not args.req_id:
        print("Error: Requirement ID required", file=sys.stderr)
        return 1
    
    aliases = get_repo_aliases()
    result = verify_requirement(args.req_id.upper(), aliases)
    
    if json_output:
        print(json.dumps(result, indent=2))
    else:
        print(f"Requirement: {result['req_id']}")
        print(f"Title: {result.get('title', 'N/A')}")
        print(f"Status: {result['status'].upper()}")
        
        if result.get("checks"):
            print("\nSource Checks:")
            for check in result["checks"]:
                icon = "✓" if check["current"] else ("⚠" if check["exists"] else "✗")
                print(f"  {icon} {check['source']}")
    
    return 0 if result.get("status") == "verified" else 1


def cmd_scan(args, json_output: bool) -> int:
    """Scan all mappings for specs."""
    results = scan_all_mappings()
    
    if json_output:
        print(json.dumps({"documents": results, "count": len(results)}, indent=2))
    else:
        print("=" * 70)
        print("SPEC SCAN RESULTS")
        print("=" * 70)
        
        for result in results[:20]:
            if result.get("uncaptured_count", 0) > 0:
                print(f"\n{result['path']}")
                print(f"  Uncaptured: {result['uncaptured_count']} | Coverage: {result['coverage']:.0%}")
    
    return 0


def cmd_coverage(args, json_output: bool) -> int:
    """Show spec coverage."""
    results = scan_all_mappings()
    summary = get_coverage_summary(results)
    
    if json_output:
        print(json.dumps(summary, indent=2))
    else:
        print(format_coverage(summary))
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Spec Capture - Extract and verify specifications",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  extract <file>    Extract specs from a document
  verify <REQ-XXX>  Verify a requirement against source
  scan              Scan all mappings for specs
  coverage          Show spec coverage summary

Examples:
  %(prog)s extract mapping/loop-sync.md --verbose
  %(prog)s verify REQ-001
  %(prog)s coverage --json
"""
    )
    
    parser.add_argument("command", choices=["extract", "verify", "scan", "coverage"],
                        help="Command to run")
    parser.add_argument("file", nargs="?", help="File path (for extract) or REQ-XXX (for verify)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    args.req_id = args.file if args.command == "verify" else None
    if args.command == "verify":
        args.file = None
    
    commands = {
        "extract": cmd_extract,
        "verify": cmd_verify,
        "scan": cmd_scan,
        "coverage": cmd_coverage
    }
    
    return commands[args.command](args, args.json)


if __name__ == "__main__":
    sys.exit(main())
