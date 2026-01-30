#!/usr/bin/env python3
"""
Find duplicate GAP-* definitions across traceability files.

Usage:
    python tools/find_gap_duplicates.py [--fix]

Reports:
    - Duplicate GAP ID definitions (same ID header in multiple places)
    - Location of each duplicate (file:line)

Exit codes:
    0 - No duplicates found
    1 - Duplicates found
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

# Pattern for GAP definition headers: ### GAP-XXX-NNN: Title
GAP_HEADER_PATTERN = re.compile(r'^### (GAP-[A-Z]+-\d+):\s*(.+)$')


def find_gap_definitions(traceability_dir: Path) -> dict[str, list[tuple[Path, int, str]]]:
    """
    Scan traceability files for GAP definitions.
    
    Returns:
        Dict mapping GAP ID -> list of (file, line_num, title) tuples
    """
    gaps = defaultdict(list)
    
    for md_file in traceability_dir.glob('*.md'):
        if md_file.name == 'gaps.md':  # Skip index file
            continue
            
        with open(md_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                match = GAP_HEADER_PATTERN.match(line.strip())
                if match:
                    gap_id = match.group(1)
                    title = match.group(2)
                    gaps[gap_id].append((md_file, line_num, title))
    
    return gaps


def find_duplicates(gaps: dict) -> dict[str, list]:
    """Filter to only GAP IDs with multiple definitions."""
    return {gap_id: locations for gap_id, locations in gaps.items() if len(locations) > 1}


def report_duplicates(duplicates: dict) -> None:
    """Print duplicate report."""
    if not duplicates:
        print("✅ No duplicate GAP definitions found.")
        return
    
    print(f"⚠️  Found {len(duplicates)} duplicate GAP ID(s):\n")
    
    for gap_id, locations in sorted(duplicates.items()):
        print(f"### {gap_id}")
        for filepath, line_num, title in locations:
            print(f"  - {filepath.name}:{line_num} — {title}")
        print()


def main():
    parser = argparse.ArgumentParser(description='Find duplicate GAP definitions')
    parser.add_argument('--fix', action='store_true', help='Show fix suggestions')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    args = parser.parse_args()
    
    # Find traceability directory
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    traceability_dir = repo_root / 'traceability'
    
    if not traceability_dir.exists():
        print(f"Error: {traceability_dir} not found", file=sys.stderr)
        sys.exit(1)
    
    # Scan for GAP definitions
    gaps = find_gap_definitions(traceability_dir)
    duplicates = find_duplicates(gaps)
    
    if args.json:
        import json
        output = {
            gap_id: [
                {"file": str(f.name), "line": l, "title": t}
                for f, l, t in locations
            ]
            for gap_id, locations in duplicates.items()
        }
        print(json.dumps(output, indent=2))
    else:
        report_duplicates(duplicates)
        
        if args.fix and duplicates:
            print("### Fix Suggestions\n")
            for gap_id, locations in duplicates.items():
                print(f"**{gap_id}**: Keep one definition, convert others to references:")
                keep = locations[0]
                print(f"  - Keep: {keep[0].name}:{keep[1]}")
                for loc in locations[1:]:
                    print(f"  - Remove/reference: {loc[0].name}:{loc[1]}")
                print()
    
    # Summary
    total_gaps = len(gaps)
    total_dupes = len(duplicates)
    print(f"---\nSummary: {total_gaps} unique GAP IDs, {total_dupes} duplicates")
    
    sys.exit(1 if duplicates else 0)


if __name__ == '__main__':
    main()
