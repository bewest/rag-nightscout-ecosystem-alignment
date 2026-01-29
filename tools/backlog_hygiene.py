#!/usr/bin/env python3
"""
Backlog queue validation and maintenance tool.

Validates queue structure, archives old items, and demotes stale work.

Usage:
    python tools/backlog_hygiene.py --check          # Check queue health
    python tools/backlog_hygiene.py --validate       # Validate structure
    python tools/backlog_hygiene.py --archive-completed --days 14
    python tools/backlog_hygiene.py --dry-run        # Preview changes

RUN Integration:
    RUN python tools/backlog_hygiene.py --check --json
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

LIVE_BACKLOG = Path("LIVE-BACKLOG.md")
ECOSYSTEM_BACKLOG = Path("docs/sdqctl-proposals/ECOSYSTEM-BACKLOG.md")
DOMAIN_BACKLOGS = Path("docs/sdqctl-proposals/backlogs")

READY_QUEUE_TARGET = (5, 10)


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse date from various formats."""
    patterns = [
        r'(\d{4}-\d{2}-\d{2})',  # 2026-01-29
        r'(\d{2}/\d{2}/\d{4})',  # 01/29/2026
    ]
    for pattern in patterns:
        match = re.search(pattern, date_str)
        if match:
            try:
                if '-' in match.group(1):
                    return datetime.strptime(match.group(1), '%Y-%m-%d')
                else:
                    return datetime.strptime(match.group(1), '%m/%d/%Y')
            except ValueError:
                continue
    return None


def check_live_backlog() -> dict:
    """Check LIVE-BACKLOG.md health."""
    result = {
        "file": str(LIVE_BACKLOG),
        "exists": LIVE_BACKLOG.exists(),
        "pending_count": 0,
        "processed_count": 0,
        "issues": [],
        "items_to_archive": []
    }
    
    if not LIVE_BACKLOG.exists():
        result["issues"].append("LIVE-BACKLOG.md not found")
        return result
    
    content = LIVE_BACKLOG.read_text(encoding='utf-8')
    
    # Count pending items (bullet points before ## Processed)
    match = re.search(r'^(.*?)^## Processed', content, re.MULTILINE | re.DOTALL)
    if match:
        header_section = match.group(1)
        pending = re.findall(r'^\s*\* (.+)$', header_section, re.MULTILINE)
        result["pending_count"] = len(pending)
        if pending:
            result["issues"].append(f"{len(pending)} pending items not processed")
    
    # Count and analyze processed items
    match = re.search(r'^## Processed\s*\n(.*?)(?=^##|\Z)', content, re.MULTILINE | re.DOTALL)
    if match:
        table_section = match.group(1)
        rows = re.findall(r'^\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|$', table_section, re.MULTILINE)
        
        # Skip header row
        data_rows = [r for r in rows if not re.match(r'\s*-+\s*', r[0]) and 'Item' not in r[0]]
        result["processed_count"] = len(data_rows)
        
        # Check for items to archive (completed items older than threshold)
        now = datetime.now()
        for row in data_rows:
            item, priority, status, date_str = [c.strip() for c in row]
            if '✅' in status:
                item_date = parse_date(date_str)
                if item_date:
                    age_days = (now - item_date).days
                    result["items_to_archive"].append({
                        "item": item,
                        "status": status,
                        "date": date_str,
                        "age_days": age_days
                    })
    
    # Validate structure
    if '## Processed' not in content:
        result["issues"].append("Missing '## Processed' section")
    
    if not re.search(r'\| Item \| Priority \| Status \| Date \|', content):
        result["issues"].append("Processed table missing proper header")
    
    return result


def check_ecosystem_backlog() -> dict:
    """Check ECOSYSTEM-BACKLOG.md health."""
    result = {
        "file": str(ECOSYSTEM_BACKLOG),
        "exists": ECOSYSTEM_BACKLOG.exists(),
        "ready_queue_count": 0,
        "ready_queue_target": list(READY_QUEUE_TARGET),
        "completed_count": 0,
        "issues": []
    }
    
    if not ECOSYSTEM_BACKLOG.exists():
        result["issues"].append("ECOSYSTEM-BACKLOG.md not found")
        return result
    
    content = ECOSYSTEM_BACKLOG.read_text(encoding='utf-8')
    
    # Count Ready Queue items
    match = re.search(r'^## Ready Queue.*?\n(.*?)(?=^## |\Z)', content, re.MULTILINE | re.DOTALL)
    if match:
        queue_section = match.group(1)
        items = re.findall(r'^### \d+\.\s*\[([^\]]+)\]\s*(.+)$', queue_section, re.MULTILINE)
        result["ready_queue_count"] = len(items)
        
        if len(items) < READY_QUEUE_TARGET[0]:
            result["issues"].append(f"Ready Queue below target ({len(items)} < {READY_QUEUE_TARGET[0]})")
        elif len(items) > READY_QUEUE_TARGET[1]:
            result["issues"].append(f"Ready Queue above target ({len(items)} > {READY_QUEUE_TARGET[1]})")
    else:
        result["issues"].append("Missing '## Ready Queue' section")
    
    # Count Completed items
    match = re.search(r'^## Completed\s*\n(.*?)(?=^##|\Z)', content, re.MULTILINE | re.DOTALL)
    if match:
        completed_section = match.group(1)
        rows = re.findall(r'^\|[^|]+\|[^|]+\|[^|]+\|$', completed_section, re.MULTILINE)
        result["completed_count"] = max(0, len(rows) - 2)  # Subtract header and separator
    
    # Validate structure
    required_sections = ['## Ready Queue', '## Backlog', '## Completed']
    for section in required_sections:
        if section not in content:
            result["issues"].append(f"Missing '{section}' section")
    
    return result


def check_domain_backlogs() -> dict:
    """Check domain backlog files."""
    result = {
        "directory": str(DOMAIN_BACKLOGS),
        "exists": DOMAIN_BACKLOGS.exists(),
        "backlogs": {},
        "issues": []
    }
    
    if not DOMAIN_BACKLOGS.exists():
        result["issues"].append("Domain backlogs directory not found")
        return result
    
    for backlog_file in DOMAIN_BACKLOGS.glob("*.md"):
        if backlog_file.name.startswith('.'):
            continue
            
        content = backlog_file.read_text(encoding='utf-8')
        backlog_result = {
            "file": backlog_file.name,
            "active_count": 0,
            "completed_count": 0,
            "issues": []
        }
        
        # Count Active Items
        match = re.search(r'^## Active Items\s*\n(.*?)(?=^##|\Z)', content, re.MULTILINE | re.DOTALL)
        if match:
            table_section = match.group(1)
            rows = re.findall(r'^\|[^|]+\|[^|]+\|[^|]+\|[^|]+\|[^|]+\|$', table_section, re.MULTILINE)
            backlog_result["active_count"] = max(0, len(rows) - 2)
        else:
            backlog_result["issues"].append("Missing '## Active Items' section")
        
        # Count Completed
        match = re.search(r'^## Completed\s*\n(.*?)(?=^##|\Z)', content, re.MULTILINE | re.DOTALL)
        if match:
            table_section = match.group(1)
            rows = re.findall(r'^\|[^|]+\|[^|]+\|[^|]+\|$', table_section, re.MULTILINE)
            backlog_result["completed_count"] = max(0, len(rows) - 2)
        
        result["backlogs"][backlog_file.name] = backlog_result
        
        if backlog_result["issues"]:
            result["issues"].extend([f"{backlog_file.name}: {i}" for i in backlog_result["issues"]])
    
    return result


def archive_completed_items(days: int, dry_run: bool = True) -> dict:
    """Archive completed items older than specified days."""
    result = {
        "archived": [],
        "kept": [],
        "dry_run": dry_run
    }
    
    if not LIVE_BACKLOG.exists():
        return result
    
    content = LIVE_BACKLOG.read_text(encoding='utf-8')
    now = datetime.now()
    cutoff = now - timedelta(days=days)
    
    # Find Processed section
    match = re.search(r'^(## Processed\s*\n\|[^\n]+\n\|[^\n]+\n)(.*?)(\Z)', content, re.MULTILINE | re.DOTALL)
    if not match:
        return result
    
    header = match.group(1)
    rows_section = match.group(2)
    
    # Parse rows
    rows = re.findall(r'^(\|[^\n]+\|)$', rows_section, re.MULTILINE)
    
    keep_rows = []
    archive_rows = []
    
    for row in rows:
        # Extract date from row
        cols = [c.strip() for c in row.split('|')[1:-1]]
        if len(cols) >= 4:
            date_str = cols[3]
            item_date = parse_date(date_str)
            
            if item_date and item_date < cutoff and '✅' in cols[2]:
                archive_rows.append(row)
                result["archived"].append({"row": row, "date": date_str})
            else:
                keep_rows.append(row)
                result["kept"].append({"row": row})
        else:
            keep_rows.append(row)
    
    if not dry_run and archive_rows:
        # Rebuild file with kept rows only
        new_rows_section = '\n'.join(keep_rows) + '\n' if keep_rows else ''
        new_content = content[:match.start(2)] + new_rows_section + content[match.end(2):]
        LIVE_BACKLOG.write_text(new_content, encoding='utf-8')
        
        # TODO: Write archived items to archive file
    
    return result


def run_check() -> dict:
    """Run full health check."""
    return {
        "live_backlog": check_live_backlog(),
        "ecosystem_backlog": check_ecosystem_backlog(),
        "domain_backlogs": check_domain_backlogs(),
        "health": "healthy",
        "recommendations": []
    }


def compute_health(check_result: dict) -> dict:
    """Compute overall health and recommendations."""
    issues = []
    recommendations = []
    
    # Collect issues from all checks
    issues.extend(check_result["live_backlog"].get("issues", []))
    issues.extend(check_result["ecosystem_backlog"].get("issues", []))
    issues.extend(check_result["domain_backlogs"].get("issues", []))
    
    # Generate recommendations
    live = check_result["live_backlog"]
    if live.get("pending_count", 0) > 0:
        recommendations.append(f"Process {live['pending_count']} pending LIVE-BACKLOG items")
    
    archive_candidates = [i for i in live.get("items_to_archive", []) if i.get("age_days", 0) > 14]
    if len(archive_candidates) > 10:
        recommendations.append(f"Archive {len(archive_candidates)} old completed items")
    
    eco = check_result["ecosystem_backlog"]
    if eco.get("ready_queue_count", 0) < READY_QUEUE_TARGET[0]:
        recommendations.append("Replenish Ready Queue from P1 backlog")
    
    # Determine health
    if any("not found" in i for i in issues):
        health = "critical"
    elif issues:
        health = "warning"
    else:
        health = "healthy"
    
    check_result["health"] = health
    check_result["recommendations"] = recommendations
    check_result["issues"] = issues
    
    return check_result


def format_check_report(result: dict) -> str:
    """Format check result as human-readable report."""
    lines = []
    lines.append("=" * 60)
    lines.append("BACKLOG HYGIENE CHECK")
    lines.append("=" * 60)
    
    # LIVE-BACKLOG
    live = result["live_backlog"]
    lines.append("")
    lines.append("LIVE-BACKLOG.md:")
    lines.append(f"  Pending: {live.get('pending_count', 0)}")
    lines.append(f"  Processed: {live.get('processed_count', 0)}")
    if live.get("items_to_archive"):
        old_items = [i for i in live["items_to_archive"] if i.get("age_days", 0) > 14]
        lines.append(f"  Archive candidates (>14d): {len(old_items)}")
    
    # ECOSYSTEM-BACKLOG
    eco = result["ecosystem_backlog"]
    lines.append("")
    lines.append("ECOSYSTEM-BACKLOG.md:")
    lines.append(f"  Ready Queue: {eco.get('ready_queue_count', 0)} (target: {READY_QUEUE_TARGET[0]}-{READY_QUEUE_TARGET[1]})")
    lines.append(f"  Completed: {eco.get('completed_count', 0)}")
    
    # Domain backlogs
    domain = result["domain_backlogs"]
    if domain.get("backlogs"):
        lines.append("")
        lines.append("DOMAIN BACKLOGS:")
        for name, info in domain["backlogs"].items():
            lines.append(f"  {name}: {info.get('active_count', 0)} active, {info.get('completed_count', 0)} completed")
    
    # Health
    lines.append("")
    lines.append(f"HEALTH: {result.get('health', 'unknown').upper()}")
    
    # Issues
    if result.get("issues"):
        lines.append("")
        lines.append("ISSUES:")
        for issue in result["issues"]:
            lines.append(f"  ⚠️ {issue}")
    
    # Recommendations
    if result.get("recommendations"):
        lines.append("")
        lines.append("RECOMMENDATIONS:")
        for rec in result["recommendations"]:
            lines.append(f"  • {rec}")
    
    lines.append("")
    lines.append("=" * 60)
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Backlog queue validation and maintenance."
    )
    parser.add_argument('--check', action='store_true', help='Check queue health')
    parser.add_argument('--validate', action='store_true', help='Validate structure')
    parser.add_argument('--archive-completed', action='store_true', help='Archive old completed items')
    parser.add_argument('--days', type=int, default=14, help='Age threshold for archiving (default: 14)')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    args = parser.parse_args()
    
    if args.archive_completed:
        result = archive_completed_items(args.days, dry_run=args.dry_run)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            action = "Would archive" if args.dry_run else "Archived"
            print(f"{action} {len(result['archived'])} items older than {args.days} days")
            if result['archived']:
                for item in result['archived'][:5]:
                    print(f"  - {item.get('date', '?')}: {item.get('row', '')[:60]}...")
                if len(result['archived']) > 5:
                    print(f"  ... and {len(result['archived']) - 5} more")
    else:
        # Default: check
        result = run_check()
        result = compute_health(result)
        
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(format_check_report(result))
        
        # Exit codes
        if result["health"] == "critical":
            sys.exit(2)
        elif result["health"] == "warning":
            sys.exit(1)
    
    sys.exit(0)


if __name__ == "__main__":
    main()
