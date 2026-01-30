#!/usr/bin/env python3
"""
Token Efficiency Dashboard - Track productivity metrics across backlog cycles.

Analyzes git history to calculate:
- Commits per day/session
- Lines changed per commit
- Files touched per commit
- Productivity trends over time

Usage:
    python tools/efficiency_dashboard.py
    python tools/efficiency_dashboard.py --days 7
    python tools/efficiency_dashboard.py --since 2026-01-29
    python tools/efficiency_dashboard.py --json
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).parent.parent


def run_git(args, cwd=None):
    """Run a git command and return output."""
    cmd = ["git", "--no-pager"] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd or PROJECT_ROOT,
            timeout=30
        )
        return result.stdout.strip()
    except Exception as e:
        return ""


def get_commits(since=None, until=None):
    """Get commit data from git log."""
    args = [
        "log",
        "--format=%H|%aI|%s",  # hash|ISO date|subject
        "--shortstat"
    ]
    
    if since:
        args.append(f"--since={since}")
    if until:
        args.append(f"--until={until}")
    
    output = run_git(args)
    
    commits = []
    lines = output.split("\n")
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        
        # Parse commit line
        if "|" in line:
            parts = line.split("|", 2)
            if len(parts) >= 3:
                commit = {
                    "hash": parts[0][:8],
                    "date": parts[1],
                    "subject": parts[2],
                    "insertions": 0,
                    "deletions": 0,
                    "files": 0,
                }
                
                # Look for stat line
                i += 1
                while i < len(lines):
                    stat_line = lines[i].strip()
                    if not stat_line:
                        i += 1
                        continue
                    
                    # Parse: " 3 files changed, 100 insertions(+), 20 deletions(-)"
                    if "file" in stat_line and "changed" in stat_line:
                        # Files
                        files_match = re.search(r"(\d+) file", stat_line)
                        if files_match:
                            commit["files"] = int(files_match.group(1))
                        
                        # Insertions
                        ins_match = re.search(r"(\d+) insertion", stat_line)
                        if ins_match:
                            commit["insertions"] = int(ins_match.group(1))
                        
                        # Deletions
                        del_match = re.search(r"(\d+) deletion", stat_line)
                        if del_match:
                            commit["deletions"] = int(del_match.group(1))
                        
                        i += 1
                        break
                    elif "|" in stat_line:
                        # Next commit, don't advance
                        break
                    else:
                        i += 1
                
                commits.append(commit)
        else:
            i += 1
    
    return commits


def get_commit_types(commits):
    """Categorize commits by type based on conventional commit prefixes."""
    types = defaultdict(int)
    
    for commit in commits:
        subject = commit["subject"].lower()
        if subject.startswith("feat"):
            types["feat"] += 1
        elif subject.startswith("fix"):
            types["fix"] += 1
        elif subject.startswith("docs"):
            types["docs"] += 1
        elif subject.startswith("refactor"):
            types["refactor"] += 1
        elif subject.startswith("test"):
            types["test"] += 1
        elif subject.startswith("chore"):
            types["chore"] += 1
        else:
            types["other"] += 1
    
    return dict(types)


def get_daily_stats(commits):
    """Group commits by day."""
    daily = defaultdict(lambda: {"commits": 0, "insertions": 0, "deletions": 0, "files": 0})
    
    for commit in commits:
        # Parse ISO date
        date_str = commit["date"][:10]  # YYYY-MM-DD
        daily[date_str]["commits"] += 1
        daily[date_str]["insertions"] += commit["insertions"]
        daily[date_str]["deletions"] += commit["deletions"]
        daily[date_str]["files"] += commit["files"]
    
    return dict(daily)


def calculate_metrics(commits):
    """Calculate efficiency metrics."""
    if not commits:
        return {
            "total_commits": 0,
            "total_insertions": 0,
            "total_deletions": 0,
            "total_files": 0,
            "net_lines": 0,
            "avg_insertions_per_commit": 0,
            "avg_files_per_commit": 0,
        }
    
    total_insertions = sum(c["insertions"] for c in commits)
    total_deletions = sum(c["deletions"] for c in commits)
    total_files = sum(c["files"] for c in commits)
    
    return {
        "total_commits": len(commits),
        "total_insertions": total_insertions,
        "total_deletions": total_deletions,
        "total_files": total_files,
        "net_lines": total_insertions - total_deletions,
        "avg_insertions_per_commit": total_insertions / len(commits) if commits else 0,
        "avg_files_per_commit": total_files / len(commits) if commits else 0,
    }


def get_tool_stats():
    """Get statistics about tools in the tools/ directory."""
    tools_dir = PROJECT_ROOT / "tools"
    if not tools_dir.exists():
        return {"count": 0, "total_lines": 0}
    
    tool_files = list(tools_dir.glob("*.py"))
    total_lines = 0
    
    for tool in tool_files:
        try:
            with open(tool, "r", encoding="utf-8") as f:
                total_lines += len(f.readlines())
        except Exception:
            pass
    
    return {
        "count": len(tool_files),
        "total_lines": total_lines,
        "tools": [t.name for t in tool_files],
    }


def print_dashboard(commits, metrics, daily, types, tools, json_output=False):
    """Print the efficiency dashboard."""
    if json_output:
        output = {
            "metrics": metrics,
            "daily": daily,
            "types": types,
            "tools": tools,
            "recent_commits": commits[:10],
        }
        print(json.dumps(output, indent=2, default=str))
        return
    
    print("=" * 70)
    print("                     EFFICIENCY DASHBOARD")
    print("=" * 70)
    
    # Overall metrics
    print("\n📊 OVERALL METRICS")
    print("-" * 40)
    print(f"  Total commits:        {metrics['total_commits']}")
    print(f"  Total insertions:     +{metrics['total_insertions']}")
    print(f"  Total deletions:      -{metrics['total_deletions']}")
    print(f"  Net lines:            {metrics['net_lines']:+d}")
    print(f"  Files touched:        {metrics['total_files']}")
    print(f"  Avg lines/commit:     {metrics['avg_insertions_per_commit']:.1f}")
    print(f"  Avg files/commit:     {metrics['avg_files_per_commit']:.1f}")
    
    # Tools statistics
    print("\n🔧 TOOLS")
    print("-" * 40)
    print(f"  Python tools:         {tools['count']}")
    print(f"  Total tool lines:     {tools['total_lines']}")
    if tools.get("tools"):
        print(f"  Recent tools:         {', '.join(tools['tools'][:5])}")
    
    # Commit types
    if types:
        print("\n📝 COMMIT TYPES")
        print("-" * 40)
        for ctype, count in sorted(types.items(), key=lambda x: -x[1]):
            bar = "█" * min(count, 20)
            print(f"  {ctype:12} {count:3d} {bar}")
    
    # Daily breakdown
    if daily:
        print("\n📅 DAILY ACTIVITY")
        print("-" * 40)
        for date in sorted(daily.keys(), reverse=True)[:7]:
            stats = daily[date]
            print(f"  {date}: {stats['commits']:2d} commits, +{stats['insertions']:-4d}/-{stats['deletions']:-4d} lines")
    
    # Recent commits
    if commits:
        print("\n🔄 RECENT COMMITS")
        print("-" * 40)
        for commit in commits[:5]:
            subject = commit["subject"][:50]
            print(f"  {commit['hash']} {subject}")
    
    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Token Efficiency Dashboard"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to analyze (default: 7)"
    )
    parser.add_argument(
        "--since",
        type=str,
        help="Start date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--until",
        type=str,
        help="End date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )
    
    args = parser.parse_args()
    
    # Determine date range
    if args.since:
        since = args.since
    else:
        since_date = datetime.now() - timedelta(days=args.days)
        since = since_date.strftime("%Y-%m-%d")
    
    until = args.until
    
    # Gather data
    commits = get_commits(since=since, until=until)
    metrics = calculate_metrics(commits)
    daily = get_daily_stats(commits)
    types = get_commit_types(commits)
    tools = get_tool_stats()
    
    # Display
    print_dashboard(commits, metrics, daily, types, tools, json_output=args.json)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
