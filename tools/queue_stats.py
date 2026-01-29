#!/usr/bin/env python3
"""
Quick queue and file status for workflow integration.

Provides one-line status for sdqctl workflow Phase 0 state checks.

Usage:
    python tools/queue_stats.py              # One-line output
    python tools/queue_stats.py --json       # JSON output
    python tools/queue_stats.py --dashboard  # Full dashboard

Output (one-line):
    Queues: LIVE=0/30 Ready=5/10 | Files: gaps=4403⚠️ reqs=2596⚠️ | Uncommitted: 11

RUN Integration:
    RUN python tools/queue_stats.py 2>/dev/null || echo "Stats: unavailable"
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Thresholds for file sizes (lines)
THRESHOLDS = {
    "traceability/gaps.md": 800,
    "traceability/requirements.md": 800,
    "progress.md": 500,
    "docs/sdqctl-proposals/ECOSYSTEM-BACKLOG.md": 500,
    "LIVE-BACKLOG.md": 100,
}

# Target range for Ready Queue
READY_QUEUE_TARGET = (5, 10)


def count_lines(path: str) -> int:
    """Count lines in a file."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return sum(1 for _ in f)
    except FileNotFoundError:
        return 0


def count_live_pending() -> int:
    """Count bullet points before ## Processed section in LIVE-BACKLOG.md."""
    try:
        content = Path("LIVE-BACKLOG.md").read_text(encoding='utf-8')
    except FileNotFoundError:
        return 0
    
    # Find content before ## Processed
    match = re.search(r'^(.*?)^## Processed', content, re.MULTILINE | re.DOTALL)
    if match:
        header_section = match.group(1)
        # Count bullet points (lines starting with *)
        return len(re.findall(r'^\s*\* ', header_section, re.MULTILINE))
    return 0


def count_live_processed() -> int:
    """Count rows in Processed table (excluding header and separator)."""
    try:
        content = Path("LIVE-BACKLOG.md").read_text(encoding='utf-8')
    except FileNotFoundError:
        return 0
    
    # Find Processed section
    match = re.search(r'^## Processed\s*\n(.*?)(?=^##|\Z)', content, re.MULTILINE | re.DOTALL)
    if match:
        table_section = match.group(1)
        # Count table rows (lines starting with |, excluding header separator |---|)
        rows = re.findall(r'^\|[^-].*\|$', table_section, re.MULTILINE)
        return max(0, len(rows) - 1)  # Subtract header row
    return 0


def count_ready_queue() -> int:
    """Count items in Ready Queue section of ECOSYSTEM-BACKLOG.md."""
    try:
        content = Path("docs/sdqctl-proposals/ECOSYSTEM-BACKLOG.md").read_text(encoding='utf-8')
    except FileNotFoundError:
        return 0
    
    # Find Ready Queue section
    match = re.search(r'^## Ready Queue.*?\n(.*?)(?=^## |\Z)', content, re.MULTILINE | re.DOTALL)
    if match:
        queue_section = match.group(1)
        # Count numbered items (### 1., ### 2., etc.)
        return len(re.findall(r'^### \d+\.', queue_section, re.MULTILINE))
    return 0


def git_status() -> tuple[int, int]:
    """Get uncommitted file counts (total, untracked)."""
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            return 0, 0
        
        lines = result.stdout.strip().split('\n') if result.stdout.strip() else []
        modified = sum(1 for l in lines if l and not l.startswith('??'))
        untracked = sum(1 for l in lines if l.startswith('??'))
        return modified + untracked, untracked
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return 0, 0


def get_last_cycle() -> tuple[str, int]:
    """Get last commit hash and cycle number if present."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            return "", 0
        
        line = result.stdout.strip()
        commit_hash = line.split()[0] if line else ""
        
        # Extract cycle number if present
        match = re.search(r'\(Cycle (\d+)\)', line)
        cycle = int(match.group(1)) if match else 0
        
        return commit_hash, cycle
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "", 0


def collect_stats() -> dict:
    """Collect all statistics."""
    live_pending = count_live_pending()
    live_processed = count_live_processed()
    ready = count_ready_queue()
    uncommitted, untracked = git_status()
    last_commit, last_cycle = get_last_cycle()
    
    files = {}
    recommendations = []
    
    for path, threshold in THRESHOLDS.items():
        lines = count_lines(path)
        over = lines > threshold
        files[path] = {
            "lines": lines,
            "threshold": threshold,
            "over": over
        }
        if over:
            recommendations.append(f"Chunk {path} ({lines} > {threshold})")
    
    # Queue health checks
    if live_pending > 0:
        recommendations.append(f"Process {live_pending} pending LIVE-BACKLOG items")
    
    if ready < READY_QUEUE_TARGET[0]:
        recommendations.append(f"Replenish Ready Queue ({ready} < {READY_QUEUE_TARGET[0]})")
    
    if uncommitted > 0:
        recommendations.append(f"Commit {uncommitted} uncommitted files")
    
    health = "healthy"
    if recommendations:
        health = "warning"
    if any(f["lines"] > f["threshold"] * 2 for f in files.values()):
        health = "critical"
    
    return {
        "queues": {
            "live_pending": live_pending,
            "live_processed": live_processed,
            "ready_queue": ready,
            "ready_queue_target": list(READY_QUEUE_TARGET)
        },
        "files": files,
        "git": {
            "uncommitted": uncommitted,
            "untracked": untracked,
            "last_commit": last_commit,
            "last_cycle": last_cycle
        },
        "health": health,
        "recommendations": recommendations
    }


def format_oneline(stats: dict) -> str:
    """Format stats as one-line output."""
    q = stats["queues"]
    f = stats["files"]
    g = stats["git"]
    
    # File stats with warning indicators
    gaps = f.get("traceability/gaps.md", {})
    reqs = f.get("traceability/requirements.md", {})
    prog = f.get("progress.md", {})
    
    gaps_warn = "⚠️" if gaps.get("over") else ""
    reqs_warn = "⚠️" if reqs.get("over") else ""
    prog_warn = "⚠️" if prog.get("over") else ""
    
    # Ready queue warning
    ready_warn = ""
    if q["ready_queue"] < q["ready_queue_target"][0]:
        ready_warn = "⚠️"
    
    return (
        f"Queues: LIVE={q['live_pending']}/{q['live_processed']} "
        f"Ready={q['ready_queue']}/{q['ready_queue_target'][1]}{ready_warn} | "
        f"Files: gaps={gaps.get('lines', 0)}{gaps_warn} "
        f"reqs={reqs.get('lines', 0)}{reqs_warn} "
        f"prog={prog.get('lines', 0)}{prog_warn} | "
        f"Uncommitted: {g['uncommitted']}"
    )


def format_dashboard(stats: dict) -> str:
    """Format stats as full dashboard."""
    lines = []
    lines.append("=" * 60)
    lines.append("WORKFLOW HYGIENE DASHBOARD")
    lines.append("=" * 60)
    
    # Queues
    q = stats["queues"]
    lines.append("")
    lines.append("QUEUES:")
    lines.append(f"  LIVE-BACKLOG:  {q['live_pending']} pending / {q['live_processed']} processed")
    lines.append(f"  Ready Queue:   {q['ready_queue']} items (target: {q['ready_queue_target'][0]}-{q['ready_queue_target'][1]})")
    
    # Files
    lines.append("")
    lines.append("FILE SIZES:")
    for path, info in stats["files"].items():
        status = "⚠️ OVER" if info["over"] else "✓"
        lines.append(f"  {path}: {info['lines']} / {info['threshold']} {status}")
    
    # Git
    g = stats["git"]
    lines.append("")
    lines.append("GIT STATUS:")
    lines.append(f"  Uncommitted: {g['uncommitted']} ({g['untracked']} untracked)")
    if g['last_cycle']:
        lines.append(f"  Last cycle:  {g['last_cycle']} ({g['last_commit']})")
    
    # Health
    lines.append("")
    lines.append(f"HEALTH: {stats['health'].upper()}")
    
    # Recommendations
    if stats["recommendations"]:
        lines.append("")
        lines.append("RECOMMENDATIONS:")
        for rec in stats["recommendations"]:
            lines.append(f"  • {rec}")
    
    lines.append("")
    lines.append("=" * 60)
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Quick queue and file status for workflow integration."
    )
    parser.add_argument(
        '--json', 
        action='store_true',
        help='Output as JSON'
    )
    parser.add_argument(
        '--dashboard', 
        action='store_true',
        help='Show full dashboard'
    )
    parser.add_argument(
        '--route',
        type=str,
        metavar='PREFIX',
        help='Show which file to use for a gap/req prefix (e.g., --route GAP-CGM)'
    )
    args = parser.parse_args()
    
    # Handle --route separately
    if args.route:
        result = route_prefix(args.route)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result["found"]:
                print(f"{result['prefix']} → {result['file']}")
            else:
                print(f"{result['prefix']} → {result['file']} (default/other)")
        sys.exit(0)
    
    stats = collect_stats()
    
    if args.json:
        print(json.dumps(stats, indent=2))
    elif args.dashboard:
        print(format_dashboard(stats))
    else:
        print(format_oneline(stats))
    
    # Exit with non-zero if health is not healthy
    if stats["health"] == "critical":
        sys.exit(2)
    elif stats["health"] == "warning":
        sys.exit(0)  # Warnings don't fail the workflow
    
    sys.exit(0)


def route_prefix(prefix: str) -> dict:
    """Determine which file to use for a given gap/req prefix."""
    prefix = prefix.upper()
    
    # Gap prefix to domain file mapping
    GAP_ROUTES = {
        "cgm-sources": ["GAP-CGM", "GAP-G7", "GAP-LIBRE", "GAP-DEXCOM", "GAP-BLE", "GAP-LIBRELINK", "GAP-SHARE", "GAP-BRIDGE", "GAP-LF"],
        "sync-identity": ["GAP-SYNC", "GAP-BATCH", "GAP-TZ", "GAP-DELEGATE"],
        "nightscout-api": ["GAP-API", "GAP-AUTH", "GAP-UI", "GAP-DB", "GAP-PLUGIN", "GAP-STATS", "GAP-ERR", "GAP-SPEC"],
        "aid-algorithms": ["GAP-ALG", "GAP-OREF", "GAP-PRED", "GAP-IOB", "GAP-CARB", "GAP-INS", "GAP-INSULIN"],
        "treatments": ["GAP-TREAT", "GAP-OVERRIDE", "GAP-REMOTE", "GAP-PROF"],
        "connectors": ["GAP-CONNECT", "GAP-TCONNECT", "GAP-NOCTURNE", "GAP-TEST"],
        "pumps": ["GAP-PUMP"],
    }
    
    # Req prefix to domain file mapping
    REQ_ROUTES = {
        "cgm-sources": ["REQ-CGM", "REQ-BLE", "REQ-LIBRE", "REQ-CONNECT", "REQ-BRIDGE"],
        "sync-identity": ["REQ-SYNC", "REQ-BATCH", "REQ-TZ"],
        "nightscout-api": ["REQ-API", "REQ-AUTH", "REQ-UI", "REQ-PLUGIN", "REQ-ERR", "REQ-STATS", "REQ-SPEC"],
        "aid-algorithms": ["REQ-ALG", "REQ-CARB", "REQ-INS", "REQ-DEGRADE", "REQ-PR"],
        "treatments": ["REQ-TREAT", "REQ-REMOTE", "REQ-ALARM", "REQ-INTEROP"],
        "pumps": ["REQ-PUMP"],
    }
    
    # Check if it's a GAP or REQ prefix
    if prefix.startswith("GAP-"):
        routes = GAP_ROUTES
        file_template = "traceability/{domain}-gaps.md"
        default_file = "traceability/gaps.md"
    elif prefix.startswith("REQ-"):
        routes = REQ_ROUTES
        file_template = "traceability/{domain}-requirements.md"
        default_file = "traceability/requirements.md"
    else:
        return {"prefix": prefix, "file": "unknown", "found": False, "error": "Prefix must start with GAP- or REQ-"}
    
    # Find matching domain
    for domain, prefixes in routes.items():
        for p in prefixes:
            if prefix.startswith(p):
                return {
                    "prefix": prefix,
                    "domain": domain,
                    "file": file_template.format(domain=domain),
                    "found": True
                }
    
    return {"prefix": prefix, "file": default_file, "found": False, "domain": "other"}


if __name__ == "__main__":
    main()
