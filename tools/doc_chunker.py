#!/usr/bin/env python3
"""
Document chunking tool for oversized files.

Analyzes and splits large documentation files by domain/category.

Usage:
    python tools/doc_chunker.py --check                    # Check which files need chunking
    python tools/doc_chunker.py --analyze traceability/gaps.md  # Analyze structure
    python tools/doc_chunker.py --plan traceability/gaps.md     # Preview chunk plan
    python tools/doc_chunker.py --chunk traceability/gaps.md    # Execute chunking

RUN Integration:
    RUN python tools/doc_chunker.py --check --json
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

# File size thresholds (lines)
THRESHOLDS = {
    "traceability/gaps.md": 800,
    "traceability/requirements.md": 800,
    "progress.md": 500,
}

# Gap prefix to domain mapping
GAP_DOMAIN_MAP = {
    "cgm-sources": ["GAP-CGM", "GAP-G7", "GAP-LIBRE", "GAP-DEXCOM", "GAP-BLE", "GAP-LIBRELINK", "GAP-SHARE", "GAP-BRIDGE", "GAP-LF"],
    "sync-identity": ["GAP-SYNC", "GAP-BATCH", "GAP-TZ", "GAP-DELEGATE"],
    "nightscout-api": ["GAP-API", "GAP-AUTH", "GAP-UI", "GAP-DB", "GAP-PLUGIN", "GAP-STATS", "GAP-ERR", "GAP-SPEC"],
    "aid-algorithms": ["GAP-ALG", "GAP-OREF", "GAP-PRED", "GAP-IOB", "GAP-CARB", "GAP-INS", "GAP-INSULIN"],
    "treatments": ["GAP-TREAT", "GAP-OVERRIDE", "GAP-REMOTE", "GAP-PROF"],
    "connectors": ["GAP-CONNECT", "GAP-TCONNECT", "GAP-NOCTURNE", "GAP-TEST"],
    "pumps": ["GAP-PUMP"],
}

# Requirement range to domain mapping
REQ_DOMAIN_MAP = {
    "core": list(range(1, 10)),          # REQ-001-009: Override behavior
    "timestamps": list(range(10, 20)),    # REQ-010-019: Timestamp handling
    "sync": list(range(30, 40)),          # REQ-030-039: Sync identity
    "treatments": list(range(40, 50)),    # REQ-040-049: Treatment sync
    "cgm": list(range(50, 60)),           # REQ-050-059: CGM data source
    "algorithms": list(range(60, 70)),    # REQ-060-069: Algorithm
}


def count_lines(path: Path) -> int:
    """Count lines in a file."""
    try:
        return sum(1 for _ in open(path, encoding='utf-8'))
    except FileNotFoundError:
        return 0


def check_files() -> dict:
    """Check which files are over threshold."""
    result = {
        "files_over_threshold": [],
        "files_ok": [],
        "recommendations": []
    }
    
    for path_str, threshold in THRESHOLDS.items():
        path = Path(path_str)
        lines = count_lines(path)
        
        file_info = {
            "file": path_str,
            "lines": lines,
            "threshold": threshold,
            "over": lines > threshold,
            "ratio": round(lines / threshold, 1) if threshold else 0
        }
        
        if lines > threshold:
            result["files_over_threshold"].append(file_info)
            result["recommendations"].append(
                f"Chunk {path_str} ({lines} > {threshold}, {file_info['ratio']}x over)"
            )
        else:
            result["files_ok"].append(file_info)
    
    return result


def get_gap_domain(gap_id: str) -> str:
    """Map a gap ID to its domain."""
    for domain, prefixes in GAP_DOMAIN_MAP.items():
        for prefix in prefixes:
            if gap_id.startswith(prefix):
                return domain
    return "other"


def get_req_domain(req_id: str) -> str:
    """Map a requirement ID to its domain."""
    # Extract number from REQ-NNN or REQ-XXX-NNN
    match = re.search(r'REQ-(?:([A-Z]+)-)?(\d+)', req_id)
    if match:
        prefix = match.group(1)
        num = int(match.group(2))
        
        if prefix:
            return prefix.lower()
        
        for domain, nums in REQ_DOMAIN_MAP.items():
            if num in nums:
                return domain
    
    return "other"


def analyze_gaps_file(path: Path) -> dict:
    """Analyze gaps.md structure."""
    result = {
        "file": str(path),
        "total_lines": count_lines(path),
        "gaps": [],
        "by_domain": defaultdict(list),
        "domain_counts": {}
    }
    
    if not path.exists():
        return result
    
    content = path.read_text(encoding='utf-8')
    
    # Find all gap headings: ### GAP-XXX-NNN: Title
    pattern = r'^### (GAP-[A-Z]+-\d+):?\s*(.*)$'
    
    current_pos = 0
    for match in re.finditer(pattern, content, re.MULTILINE):
        gap_id = match.group(1)
        title = match.group(2).strip()
        domain = get_gap_domain(gap_id)
        
        gap_info = {
            "id": gap_id,
            "title": title,
            "domain": domain,
            "line": content[:match.start()].count('\n') + 1
        }
        
        result["gaps"].append(gap_info)
        result["by_domain"][domain].append(gap_info)
    
    result["domain_counts"] = {d: len(gaps) for d, gaps in result["by_domain"].items()}
    
    return result


def analyze_requirements_file(path: Path) -> dict:
    """Analyze requirements.md structure."""
    result = {
        "file": str(path),
        "total_lines": count_lines(path),
        "requirements": [],
        "by_domain": defaultdict(list),
        "domain_counts": {}
    }
    
    if not path.exists():
        return result
    
    content = path.read_text(encoding='utf-8')
    
    # Find all requirement headings: ### REQ-NNN: Title or ### REQ-XXX-NNN: Title
    pattern = r'^### (REQ-(?:[A-Z]+-)?(?:\d+)):?\s*(.*)$'
    
    for match in re.finditer(pattern, content, re.MULTILINE):
        req_id = match.group(1)
        title = match.group(2).strip()
        domain = get_req_domain(req_id)
        
        req_info = {
            "id": req_id,
            "title": title,
            "domain": domain,
            "line": content[:match.start()].count('\n') + 1
        }
        
        result["requirements"].append(req_info)
        result["by_domain"][domain].append(req_info)
    
    result["domain_counts"] = {d: len(reqs) for d, reqs in result["by_domain"].items()}
    
    return result


def analyze_progress_file(path: Path) -> dict:
    """Analyze progress.md structure by date."""
    result = {
        "file": str(path),
        "total_lines": count_lines(path),
        "entries": [],
        "by_month": defaultdict(list),
        "month_counts": {}
    }
    
    if not path.exists():
        return result
    
    content = path.read_text(encoding='utf-8')
    
    # Find all progress entries: ### Title (YYYY-MM-DD)
    pattern = r'^### (.+?)\s*\((\d{4}-\d{2}-\d{2})\)$'
    
    for match in re.finditer(pattern, content, re.MULTILINE):
        title = match.group(1).strip()
        date_str = match.group(2)
        month = date_str[:7]  # YYYY-MM
        
        entry_info = {
            "title": title,
            "date": date_str,
            "month": month,
            "line": content[:match.start()].count('\n') + 1
        }
        
        result["entries"].append(entry_info)
        result["by_month"][month].append(entry_info)
    
    result["month_counts"] = {m: len(entries) for m, entries in result["by_month"].items()}
    
    return result


def plan_gaps_chunking(analysis: dict) -> dict:
    """Generate chunking plan for gaps.md."""
    plan = {
        "source": analysis["file"],
        "current_lines": analysis["total_lines"],
        "threshold": THRESHOLDS.get("traceability/gaps.md", 800),
        "strategy": "domain-aligned",
        "index_file": "traceability/gaps.md",
        "chunks": [],
        "estimated_index_lines": 100,
        "warnings": []
    }
    
    # Estimate lines per gap (average)
    total_gaps = len(analysis["gaps"])
    if total_gaps > 0:
        avg_lines_per_gap = analysis["total_lines"] / total_gaps
    else:
        avg_lines_per_gap = 25  # Default estimate
    
    for domain, gaps in analysis["by_domain"].items():
        if domain == "other" and len(gaps) < 3:
            continue  # Skip small "other" category
            
        chunk_file = f"traceability/{domain}-gaps.md"
        estimated_lines = int(len(gaps) * avg_lines_per_gap)
        
        chunk_info = {
            "file": chunk_file,
            "domain": domain,
            "gap_count": len(gaps),
            "gap_ids": [g["id"] for g in gaps],
            "estimated_lines": estimated_lines
        }
        plan["chunks"].append(chunk_info)
        
        if estimated_lines > plan["threshold"]:
            plan["warnings"].append(
                f"{chunk_file} will be over threshold ({estimated_lines} > {plan['threshold']})"
            )
    
    return plan


def plan_requirements_chunking(analysis: dict) -> dict:
    """Generate chunking plan for requirements.md."""
    plan = {
        "source": analysis["file"],
        "current_lines": analysis["total_lines"],
        "threshold": THRESHOLDS.get("traceability/requirements.md", 800),
        "strategy": "domain-aligned",
        "index_file": "traceability/requirements.md",
        "chunks": [],
        "estimated_index_lines": 100,
        "warnings": []
    }
    
    total_reqs = len(analysis["requirements"])
    if total_reqs > 0:
        avg_lines_per_req = analysis["total_lines"] / total_reqs
    else:
        avg_lines_per_req = 20
    
    for domain, reqs in analysis["by_domain"].items():
        if domain == "other" and len(reqs) < 3:
            continue
            
        chunk_file = f"traceability/{domain}-requirements.md"
        estimated_lines = int(len(reqs) * avg_lines_per_req)
        
        chunk_info = {
            "file": chunk_file,
            "domain": domain,
            "req_count": len(reqs),
            "req_ids": [r["id"] for r in reqs],
            "estimated_lines": estimated_lines
        }
        plan["chunks"].append(chunk_info)
    
    return plan


def plan_progress_chunking(analysis: dict, keep_months: int = 1) -> dict:
    """Generate chunking plan for progress.md (by month)."""
    plan = {
        "source": analysis["file"],
        "current_lines": analysis["total_lines"],
        "threshold": THRESHOLDS.get("progress.md", 500),
        "strategy": "by-date",
        "keep_months": keep_months,
        "archive_dir": "progress-archive",
        "chunks": [],
        "warnings": []
    }
    
    # Sort months
    months = sorted(analysis["by_month"].keys(), reverse=True)
    
    if not months:
        return plan
    
    # Keep recent months in main file
    recent_months = months[:keep_months]
    archive_months = months[keep_months:]
    
    plan["keep_in_main"] = recent_months
    
    for month in archive_months:
        entries = analysis["by_month"][month]
        chunk_info = {
            "file": f"progress-archive/{month}.md",
            "month": month,
            "entry_count": len(entries),
            "entries": [e["title"] for e in entries]
        }
        plan["chunks"].append(chunk_info)
    
    return plan


def format_check_report(result: dict) -> str:
    """Format check result as human-readable report."""
    lines = []
    lines.append("=" * 60)
    lines.append("DOCUMENT SIZE CHECK")
    lines.append("=" * 60)
    
    if result["files_over_threshold"]:
        lines.append("")
        lines.append("FILES OVER THRESHOLD:")
        for f in result["files_over_threshold"]:
            lines.append(f"  ⚠️ {f['file']}: {f['lines']} / {f['threshold']} ({f['ratio']}x)")
    
    if result["files_ok"]:
        lines.append("")
        lines.append("FILES OK:")
        for f in result["files_ok"]:
            lines.append(f"  ✓ {f['file']}: {f['lines']} / {f['threshold']}")
    
    if result["recommendations"]:
        lines.append("")
        lines.append("RECOMMENDATIONS:")
        for rec in result["recommendations"]:
            lines.append(f"  • {rec}")
    
    lines.append("")
    lines.append("=" * 60)
    
    return "\n".join(lines)


def format_analysis_report(analysis: dict, file_type: str) -> str:
    """Format analysis as human-readable report."""
    lines = []
    lines.append("=" * 60)
    lines.append(f"ANALYSIS: {analysis['file']}")
    lines.append("=" * 60)
    lines.append(f"Total lines: {analysis['total_lines']}")
    
    if file_type == "gaps":
        lines.append(f"Total gaps: {len(analysis['gaps'])}")
        lines.append("")
        lines.append("BY DOMAIN:")
        for domain, count in sorted(analysis["domain_counts"].items(), key=lambda x: -x[1]):
            lines.append(f"  {domain}: {count} gaps")
    
    elif file_type == "requirements":
        lines.append(f"Total requirements: {len(analysis['requirements'])}")
        lines.append("")
        lines.append("BY DOMAIN:")
        for domain, count in sorted(analysis["domain_counts"].items(), key=lambda x: -x[1]):
            lines.append(f"  {domain}: {count} requirements")
    
    elif file_type == "progress":
        lines.append(f"Total entries: {len(analysis['entries'])}")
        lines.append("")
        lines.append("BY MONTH:")
        for month, count in sorted(analysis["month_counts"].items(), reverse=True):
            lines.append(f"  {month}: {count} entries")
    
    lines.append("")
    lines.append("=" * 60)
    
    return "\n".join(lines)


def format_plan_report(plan: dict) -> str:
    """Format chunking plan as human-readable report."""
    lines = []
    lines.append("=" * 60)
    lines.append(f"CHUNKING PLAN: {plan['source']}")
    lines.append("=" * 60)
    lines.append(f"Current: {plan['current_lines']} lines")
    lines.append(f"Threshold: {plan['threshold']} lines")
    lines.append(f"Strategy: {plan['strategy']}")
    lines.append("")
    lines.append("PROPOSED CHUNKS:")
    
    for chunk in plan["chunks"]:
        if "gap_count" in chunk:
            lines.append(f"  {chunk['file']}: {chunk['gap_count']} gaps (~{chunk['estimated_lines']} lines)")
        elif "req_count" in chunk:
            lines.append(f"  {chunk['file']}: {chunk['req_count']} requirements (~{chunk['estimated_lines']} lines)")
        elif "entry_count" in chunk:
            lines.append(f"  {chunk['file']}: {chunk['entry_count']} entries")
    
    if plan.get("warnings"):
        lines.append("")
        lines.append("WARNINGS:")
        for warn in plan["warnings"]:
            lines.append(f"  ⚠️ {warn}")
    
    lines.append("")
    lines.append("=" * 60)
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Document chunking tool for oversized files."
    )
    parser.add_argument('--check', action='store_true', help='Check which files need chunking')
    parser.add_argument('--analyze', type=str, help='Analyze file structure')
    parser.add_argument('--plan', type=str, help='Generate chunking plan')
    parser.add_argument('--chunk', type=str, help='Execute chunking (not yet implemented)')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    args = parser.parse_args()
    
    if args.analyze:
        path = Path(args.analyze)
        if 'gaps' in str(path):
            analysis = analyze_gaps_file(path)
            file_type = "gaps"
        elif 'requirements' in str(path):
            analysis = analyze_requirements_file(path)
            file_type = "requirements"
        elif 'progress' in str(path):
            analysis = analyze_progress_file(path)
            file_type = "progress"
        else:
            print(f"Unknown file type: {path}", file=sys.stderr)
            sys.exit(1)
        
        if args.json:
            # Convert defaultdict to dict for JSON
            if "by_domain" in analysis:
                analysis["by_domain"] = dict(analysis["by_domain"])
            if "by_month" in analysis:
                analysis["by_month"] = dict(analysis["by_month"])
            print(json.dumps(analysis, indent=2))
        else:
            print(format_analysis_report(analysis, file_type))
    
    elif args.plan:
        path = Path(args.plan)
        if 'gaps' in str(path):
            analysis = analyze_gaps_file(path)
            plan = plan_gaps_chunking(analysis)
        elif 'requirements' in str(path):
            analysis = analyze_requirements_file(path)
            plan = plan_requirements_chunking(analysis)
        elif 'progress' in str(path):
            analysis = analyze_progress_file(path)
            plan = plan_progress_chunking(analysis)
        else:
            print(f"Unknown file type: {path}", file=sys.stderr)
            sys.exit(1)
        
        if args.json:
            print(json.dumps(plan, indent=2))
        else:
            print(format_plan_report(plan))
    
    elif args.chunk:
        print("Chunking execution not yet implemented.", file=sys.stderr)
        print("Use --plan to preview, then manually execute.", file=sys.stderr)
        sys.exit(1)
    
    else:
        # Default: check
        result = check_files()
        
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(format_check_report(result))
        
        # Exit with warning if files over threshold
        if result["files_over_threshold"]:
            sys.exit(1)
    
    sys.exit(0)


if __name__ == "__main__":
    main()
