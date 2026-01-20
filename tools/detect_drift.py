#!/usr/bin/env python3
"""
Drift Detector - Detects when documentation drifts from source code.

Compares timestamps and validates that code references still match source files.
Identifies stale documentation that may need updates after source code changes.

Usage:
    # Check all documents for drift
    python tools/detect_drift.py

    # Check specific document
    python tools/detect_drift.py --file mapping/loop-sync.md

    # Show only stale documents
    python tools/detect_drift.py --stale-only

    # JSON output for agents
    python tools/detect_drift.py --json

    # Verbose output with details
    python tools/detect_drift.py --verbose

For AI agents:
    python tools/detect_drift.py --json | jq '.stale_documents[]'
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).parent.parent
EXTERNALS_DIR = WORKSPACE_ROOT / "externals"
MAPPING_DIR = WORKSPACE_ROOT / "mapping"
DOCS_DIR = WORKSPACE_ROOT / "docs"
LOCKFILE = WORKSPACE_ROOT / "workspace.lock.json"

CODE_REF_PATTERN = re.compile(r'`([a-zA-Z][a-zA-Z0-9_-]{0,15}):([a-zA-Z0-9_./-]+)(?:#(.+))?`')
LINE_REF_PATTERN = re.compile(r'L(\d+)(?:-L?(\d+))?')


def load_lockfile() -> dict:
    """Load workspace lock file with repo information."""
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


def get_file_mtime(path: Path) -> datetime:
    """Get file modification time as datetime."""
    try:
        stat = path.stat()
        return datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    except OSError:
        return datetime.min.replace(tzinfo=timezone.utc)


def get_repo_latest_mtime(repo_name: str) -> datetime:
    """Get the latest modification time of any file in a repo."""
    repo_path = EXTERNALS_DIR / repo_name
    
    if not repo_path.exists():
        return datetime.min.replace(tzinfo=timezone.utc)
    
    latest = datetime.min.replace(tzinfo=timezone.utc)
    
    try:
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for f in files[:100]:
                file_path = Path(root) / f
                mtime = get_file_mtime(file_path)
                if mtime > latest:
                    latest = mtime
    except Exception:
        pass
    
    return latest


def parse_code_refs(content: str) -> list:
    """Extract code references from document content."""
    refs = []
    
    for match in CODE_REF_PATTERN.finditer(content):
        alias = match.group(1)
        file_path = match.group(2)
        anchor = match.group(3)
        
        if alias in ['http', 'https', 'ftp', 'mailto', 'alias']:
            continue
        
        line_start = None
        line_end = None
        
        if anchor:
            line_match = LINE_REF_PATTERN.match(anchor)
            if line_match:
                line_start = int(line_match.group(1))
                line_end = int(line_match.group(2)) if line_match.group(2) else line_start
        
        refs.append({
            "alias": alias,
            "path": file_path,
            "anchor": anchor,
            "line_start": line_start,
            "line_end": line_end,
            "raw": match.group(0)
        })
    
    return refs


def check_ref_exists(ref: dict, aliases: dict) -> dict:
    """Check if a code reference resolves to an existing file."""
    alias = ref["alias"]
    
    if alias not in aliases:
        return {
            "exists": False,
            "reason": f"Unknown alias: {alias}",
            "resolved_path": None
        }
    
    repo_name = aliases[alias]
    file_path = EXTERNALS_DIR / repo_name / ref["path"]
    
    if not file_path.exists():
        return {
            "exists": False,
            "reason": f"File not found: {ref['path']}",
            "resolved_path": str(file_path.relative_to(WORKSPACE_ROOT))
        }
    
    return {
        "exists": True,
        "reason": None,
        "resolved_path": str(file_path.relative_to(WORKSPACE_ROOT)),
        "file_mtime": get_file_mtime(file_path).isoformat()
    }


def analyze_document(doc_path: Path, aliases: dict) -> dict:
    """Analyze a document for drift."""
    relative_path = str(doc_path.relative_to(WORKSPACE_ROOT))
    doc_mtime = get_file_mtime(doc_path)
    
    try:
        content = doc_path.read_text(errors="ignore")
    except Exception as e:
        return {
            "path": relative_path,
            "error": str(e),
            "status": "error"
        }
    
    code_refs = parse_code_refs(content)
    
    stale_reasons = []
    broken_refs = []
    referenced_repos = set()
    
    for ref in code_refs:
        check_result = check_ref_exists(ref, aliases)
        
        if not check_result["exists"]:
            broken_refs.append({
                "ref": ref["raw"],
                "reason": check_result["reason"]
            })
        elif ref["alias"] in aliases:
            referenced_repos.add(aliases[ref["alias"]])
    
    for repo_name in referenced_repos:
        repo_mtime = get_repo_latest_mtime(repo_name)
        if repo_mtime > doc_mtime:
            days_stale = (repo_mtime - doc_mtime).days
            stale_reasons.append({
                "repo": repo_name,
                "repo_updated": repo_mtime.isoformat(),
                "doc_updated": doc_mtime.isoformat(),
                "days_stale": days_stale
            })
    
    is_stale = len(stale_reasons) > 0
    has_broken_refs = len(broken_refs) > 0
    
    if is_stale and has_broken_refs:
        status = "critical"
    elif is_stale:
        status = "stale"
    elif has_broken_refs:
        status = "broken_refs"
    else:
        status = "current"
    
    return {
        "path": relative_path,
        "status": status,
        "doc_modified": doc_mtime.isoformat(),
        "code_refs_count": len(code_refs),
        "referenced_repos": list(referenced_repos),
        "stale_reasons": stale_reasons,
        "broken_refs": broken_refs,
        "is_stale": is_stale,
        "has_broken_refs": has_broken_refs
    }


def scan_documents() -> list:
    """Scan all mapping and docs for drift."""
    aliases = get_repo_aliases()
    results = []
    
    scan_dirs = [MAPPING_DIR, DOCS_DIR / "10-domain", DOCS_DIR / "60-research"]
    
    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        
        for md_file in scan_dir.rglob("*.md"):
            if md_file.name.startswith("_"):
                continue
            
            result = analyze_document(md_file, aliases)
            results.append(result)
    
    results.sort(key=lambda x: {
        "critical": 0,
        "stale": 1,
        "broken_refs": 2,
        "current": 3,
        "error": 4
    }.get(x.get("status", "error"), 5))
    
    return results


def get_drift_summary(results: list) -> dict:
    """Generate summary of drift analysis."""
    summary = {
        "total_documents": len(results),
        "stale_count": 0,
        "broken_refs_count": 0,
        "critical_count": 0,
        "current_count": 0,
        "stale_documents": [],
        "broken_ref_documents": [],
        "referenced_repos": set()
    }
    
    for result in results:
        status = result.get("status", "error")
        
        if status == "critical":
            summary["critical_count"] += 1
            summary["stale_documents"].append(result["path"])
            summary["broken_ref_documents"].append(result["path"])
        elif status == "stale":
            summary["stale_count"] += 1
            summary["stale_documents"].append(result["path"])
        elif status == "broken_refs":
            summary["broken_refs_count"] += 1
            summary["broken_ref_documents"].append(result["path"])
        elif status == "current":
            summary["current_count"] += 1
        
        for repo in result.get("referenced_repos", []):
            summary["referenced_repos"].add(repo)
    
    summary["referenced_repos"] = list(summary["referenced_repos"])
    
    if summary["critical_count"] > 0:
        summary["health"] = "critical"
    elif summary["stale_count"] > summary["current_count"]:
        summary["health"] = "needs_attention"
    elif summary["stale_count"] > 0:
        summary["health"] = "minor_drift"
    else:
        summary["health"] = "healthy"
    
    return summary


def format_results(results: list, stale_only: bool, verbose: bool) -> str:
    """Format results for human display."""
    output = []
    output.append("=" * 70)
    output.append("DRIFT DETECTION REPORT")
    output.append("=" * 70)
    
    summary = get_drift_summary(results)
    
    output.append(f"\nHealth: {summary['health'].upper()}")
    output.append(f"Total Documents: {summary['total_documents']}")
    output.append(f"  Current: {summary['current_count']}")
    output.append(f"  Stale: {summary['stale_count']}")
    output.append(f"  Broken Refs: {summary['broken_refs_count']}")
    output.append(f"  Critical: {summary['critical_count']}")
    
    if stale_only:
        filtered = [r for r in results if r.get("is_stale") or r.get("has_broken_refs")]
    else:
        filtered = results
    
    if filtered:
        output.append("\n" + "-" * 70)
        output.append("DOCUMENTS")
        output.append("-" * 70)
        
        for result in filtered:
            status_icon = {
                "critical": "🔴",
                "stale": "🟡",
                "broken_refs": "🟠",
                "current": "🟢",
                "error": "⚪"
            }.get(result.get("status", "error"), "⚪")
            
            output.append(f"\n{status_icon} {result['path']}")
            output.append(f"   Status: {result.get('status', 'unknown')}")
            output.append(f"   Modified: {result.get('doc_modified', 'unknown')}")
            output.append(f"   Code Refs: {result.get('code_refs_count', 0)}")
            
            if verbose:
                if result.get("stale_reasons"):
                    output.append("   Stale because:")
                    for reason in result["stale_reasons"]:
                        output.append(f"     - {reason['repo']} updated {reason['days_stale']} days after doc")
                
                if result.get("broken_refs"):
                    output.append("   Broken refs:")
                    for br in result["broken_refs"][:5]:
                        output.append(f"     - {br['ref']}: {br['reason']}")
    
    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(
        description="Drift Detector - Detect documentation drift from source code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Check all documents
  %(prog)s --stale-only       # Show only stale documents
  %(prog)s --file mapping/x.md  # Check specific document
  %(prog)s --json             # JSON output for agents
"""
    )
    
    parser.add_argument("--file", help="Check specific document")
    parser.add_argument("--stale-only", action="store_true", help="Show only stale documents")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    aliases = get_repo_aliases()
    
    if args.file:
        doc_path = WORKSPACE_ROOT / args.file
        if not doc_path.exists():
            if args.json:
                print(json.dumps({"error": f"File not found: {args.file}"}))
            else:
                print(f"Error: File not found: {args.file}", file=sys.stderr)
            return 1
        
        result = analyze_document(doc_path, aliases)
        
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(format_results([result], args.stale_only, args.verbose))
        
        return 0 if result.get("status") == "current" else 1
    
    results = scan_documents()
    summary = get_drift_summary(results)
    
    if args.json:
        output = {
            "summary": summary,
            "documents": results
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_results(results, args.stale_only, args.verbose))
    
    if summary["health"] == "critical":
        return 2
    elif summary["health"] in ["needs_attention", "minor_drift"]:
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
