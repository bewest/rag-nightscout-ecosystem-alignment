#!/usr/bin/env python3
"""
Reference Validator - verifies code references in mapping documents resolve to actual files.

Scans mapping documents for code reference patterns like:
- `alias:path/to/file.ext`
- `alias:path/to/file.ext#L10-L50`

Validates that:
1. The alias matches a known repository in workspace.lock.json
2. The referenced file exists in externals/<repo>/

Usage:
    python tools/verify_refs.py              # Validate all references
    python tools/verify_refs.py --verbose    # Show all refs, not just broken
    python tools/verify_refs.py --json       # Output JSON report
    python tools/verify_refs.py --fix-stale  # Suggest fixes for stale refs

Outputs:
    traceability/refs-validation.json  - Machine-readable validation report
    traceability/refs-validation.md    - Human-readable validation report
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).parent.parent
LOCKFILE = WORKSPACE_ROOT / "workspace.lock.json"
MAPPING_DIR = WORKSPACE_ROOT / "mapping"
DOCS_DIR = WORKSPACE_ROOT / "docs"
TRACEABILITY_DIR = WORKSPACE_ROOT / "traceability"
EXTERNALS_DIR = WORKSPACE_ROOT / "externals"

CODE_REF_PATTERN = re.compile(r'`([a-zA-Z0-9_-]+:[^`]+)`')
X_AID_SOURCE_PATTERN = re.compile(r'x-aid-source:\s*["\']?([^"\'>\s]+)["\']?', re.IGNORECASE)


def parse_code_ref(ref_string):
    """
    Parse a code reference like 'crm:lib/server/treatments.js#L10-L50'.
    Returns (alias, path, anchor) or None if invalid.
    
    Valid code refs must:
    - Start with a known alias pattern (lowercase, short)
    - Have a path that looks like a file path (contains / or .)
    - Not look like JSON key:value patterns
    - Not be URL schemes (e.g., http://, https://, caregiver://)
    
    Aligned with linkcheck.py filtering logic.
    """
    if re.search(r':\s*["\'\[]', ref_string) or ' ' in ref_string:
        return None
    
    # Skip URL schemes (path starts with //)
    if re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*://', ref_string):
        return None
    
    # Skip example/placeholder patterns
    if ref_string.startswith('alias:'):
        return None
    
    match = re.match(r'^([a-zA-Z][a-zA-Z0-9_-]{0,15}):([a-zA-Z0-9_./-]+)(?:#(.+))?$', ref_string)
    if match:
        path = match.group(2)
        if '/' in path or '.' in path:
            return match.group(1), path, match.group(3)
    return None


def load_lockfile():
    """Load workspace.lock.json and build alias mapping."""
    if not LOCKFILE.exists():
        print(f"Warning: {LOCKFILE} not found")
        return {}, "externals"
    
    with open(LOCKFILE) as f:
        data = json.load(f)
    
    externals_dir = data.get("externals_dir", "externals")
    aliases = {}
    
    for repo in data.get("repos", []):
        repo_info = {
            "name": repo["name"],
            "local_path": WORKSPACE_ROOT / externals_dir / repo["name"],
            "url": repo.get("url", ""),
            "ref": repo.get("ref", "main")
        }
        alias = repo.get("alias", repo["name"])
        aliases[alias] = repo_info
        for extra_alias in repo.get("aliases", []):
            aliases[extra_alias] = repo_info
    
    return aliases, externals_dir


def extract_refs_from_file(filepath):
    """Extract all code references from a file."""
    refs = []
    try:
        content = filepath.read_text(errors="ignore")
        
        for match in CODE_REF_PATTERN.finditer(content):
            ref_string = match.group(1)
            parsed = parse_code_ref(ref_string)
            if parsed is None:
                continue
            
            alias, path, anchor = parsed
            line_num = content[:match.start()].count('\n') + 1
            refs.append({
                "alias": alias,
                "path": path,
                "anchor": anchor,
                "line": line_num,
                "raw": match.group(0),
                "source_file": str(filepath.relative_to(WORKSPACE_ROOT))
            })
        
        for match in X_AID_SOURCE_PATTERN.finditer(content):
            line_num = content[:match.start()].count('\n') + 1
            ref_str = match.group(1)
            if ':' in ref_str:
                parts = ref_str.split(':', 1)
                if len(parts) == 2:
                    alias, path = parts
                    anchor = None
                    if '#' in path:
                        path, anchor = path.split('#', 1)
                    refs.append({
                        "alias": alias,
                        "path": path,
                        "anchor": anchor,
                        "line": line_num,
                        "raw": ref_str,
                        "source_file": str(filepath.relative_to(WORKSPACE_ROOT)),
                        "type": "x-aid-source"
                    })
    
    except Exception as e:
        print(f"Warning: Could not read {filepath}: {e}")
    
    return refs


def validate_ref(ref, aliases):
    """Validate a single reference."""
    alias = ref["alias"]
    path = ref["path"]
    
    if alias not in aliases:
        return {
            "status": "unknown_alias",
            "message": f"Unknown alias '{alias}'. Known aliases: {', '.join(sorted(aliases.keys()))}"
        }
    
    repo_info = aliases[alias]
    local_path = repo_info["local_path"]
    
    if not local_path.exists():
        return {
            "status": "repo_missing",
            "message": f"Repository not cloned at {local_path}"
        }
    
    file_path = local_path / path
    
    if file_path.exists():
        return {
            "status": "valid",
            "resolved_path": str(file_path.relative_to(WORKSPACE_ROOT))
        }
    
    parent_dir = file_path.parent
    if parent_dir.exists():
        similar = [f.name for f in parent_dir.iterdir() if f.is_file()][:5]
        return {
            "status": "file_not_found",
            "message": f"File not found: {path}",
            "searched_in": str(local_path.relative_to(WORKSPACE_ROOT)),
            "similar_files": similar
        }
    
    return {
        "status": "path_not_found",
        "message": f"Path not found: {path}",
        "searched_in": str(local_path.relative_to(WORKSPACE_ROOT))
    }


def scan_directory(directory, aliases, file_patterns=("*.md", "*.yaml", "*.yml")):
    """Scan a directory for files and extract/validate references."""
    results = []
    
    for pattern in file_patterns:
        for filepath in directory.rglob(pattern):
            if filepath.name.startswith('_'):
                continue
            
            refs = extract_refs_from_file(filepath)
            for ref in refs:
                validation = validate_ref(ref, aliases)
                results.append({
                    **ref,
                    **validation
                })
    
    return results


def generate_report(results, aliases):
    """Generate validation report."""
    by_status = defaultdict(list)
    by_file = defaultdict(list)
    by_alias = defaultdict(list)
    
    for r in results:
        by_status[r["status"]].append(r)
        by_file[r["source_file"]].append(r)
        by_alias[r["alias"]].append(r)
    
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_refs": len(results),
            "valid": len(by_status.get("valid", [])),
            "unknown_alias": len(by_status.get("unknown_alias", [])),
            "repo_missing": len(by_status.get("repo_missing", [])),
            "file_not_found": len(by_status.get("file_not_found", [])),
            "path_not_found": len(by_status.get("path_not_found", []))
        },
        "known_aliases": list(aliases.keys()),
        "by_status": {
            status: [
                {
                    "source_file": r["source_file"],
                    "line": r["line"],
                    "ref": r["raw"],
                    "message": r.get("message", "")
                }
                for r in refs
            ]
            for status, refs in by_status.items()
            if status != "valid"
        },
        "by_file": {
            f: {
                "total": len(refs),
                "valid": len([r for r in refs if r["status"] == "valid"]),
                "broken": len([r for r in refs if r["status"] != "valid"])
            }
            for f, refs in by_file.items()
        }
    }
    
    return report


def generate_markdown(report):
    """Generate human-readable markdown report."""
    lines = [
        "# Code Reference Validation Report",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"| Metric | Count |",
        f"|--------|-------|",
        f"| Total References | {report['summary']['total_refs']} |",
        f"| Valid | {report['summary']['valid']} |",
        f"| Unknown Alias | {report['summary']['unknown_alias']} |",
        f"| Repository Missing | {report['summary']['repo_missing']} |",
        f"| File Not Found | {report['summary']['file_not_found']} |",
        f"| Path Not Found | {report['summary']['path_not_found']} |",
        "",
    ]
    
    broken_count = (
        report['summary']['unknown_alias'] +
        report['summary']['repo_missing'] +
        report['summary']['file_not_found'] +
        report['summary']['path_not_found']
    )
    
    if broken_count == 0:
        lines.extend([
            "**All references validated successfully.**",
            ""
        ])
    else:
        lines.extend([
            f"**{broken_count} broken references found.**",
            ""
        ])
    
    if report["by_status"]:
        lines.extend([
            "## Broken References",
            ""
        ])
        
        for status, refs in report["by_status"].items():
            lines.extend([
                f"### {status.replace('_', ' ').title()} ({len(refs)})",
                ""
            ])
            
            for ref in refs[:20]:
                lines.append(f"- `{ref['source_file']}` line {ref['line']}: `{ref['ref']}`")
                if ref.get("message"):
                    lines.append(f"  - {ref['message']}")
            
            if len(refs) > 20:
                lines.append(f"- ... and {len(refs) - 20} more")
            
            lines.append("")
    
    lines.extend([
        "## Known Aliases",
        "",
        "| Alias | Repository |",
        "|-------|------------|"
    ])
    
    for alias in sorted(report["known_aliases"]):
        lines.append(f"| `{alias}` | See workspace.lock.json |")
    
    lines.append("")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Validate code references in mapping documents")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all references")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    parser.add_argument("--no-write", action="store_true", help="Don't write output files")
    args = parser.parse_args()
    
    aliases, externals_dir = load_lockfile()
    
    if not aliases:
        print("Error: No repositories configured in workspace.lock.json")
        return 1
    
    print(f"Loaded {len(aliases)} repository aliases")
    
    all_results = []
    
    if MAPPING_DIR.exists():
        print(f"Scanning {MAPPING_DIR}...")
        all_results.extend(scan_directory(MAPPING_DIR, aliases))
    
    if DOCS_DIR.exists():
        print(f"Scanning {DOCS_DIR}...")
        all_results.extend(scan_directory(DOCS_DIR, aliases))
    
    specs_dir = WORKSPACE_ROOT / "specs"
    if specs_dir.exists():
        print(f"Scanning {specs_dir}...")
        all_results.extend(scan_directory(specs_dir, aliases))
    
    report = generate_report(all_results, aliases)
    
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"\nValidation Results:")
        print(f"  Total references: {report['summary']['total_refs']}")
        print(f"  Valid: {report['summary']['valid']}")
        print(f"  Broken: {report['summary']['total_refs'] - report['summary']['valid']}")
        
        if report["by_status"]:
            print("\nBroken References:")
            for status, refs in report["by_status"].items():
                print(f"\n  {status} ({len(refs)}):")
                for ref in refs[:5]:
                    print(f"    - {ref['source_file']}:{ref['line']} {ref['ref']}")
                if len(refs) > 5:
                    print(f"    ... and {len(refs) - 5} more")
    
    if not args.no_write:
        TRACEABILITY_DIR.mkdir(parents=True, exist_ok=True)
        
        json_path = TRACEABILITY_DIR / "refs-validation.json"
        with open(json_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nWrote: {json_path}")
        
        md_path = TRACEABILITY_DIR / "refs-validation.md"
        with open(md_path, "w") as f:
            f.write(generate_markdown(report))
        print(f"Wrote: {md_path}")
    
    broken_count = report['summary']['total_refs'] - report['summary']['valid']
    return 1 if broken_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
