#!/usr/bin/env python3
"""
Check if documented GAP issues are still open or potentially resolved.

Usage:
    python tools/verify_gap_freshness.py --gap GAP-G7-001
    python tools/verify_gap_freshness.py --sample 10
    python tools/verify_gap_freshness.py --all --json
"""

import argparse
import json
import os
import random
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

WORKSPACE_ROOT = Path(__file__).parent.parent
TRACEABILITY_DIR = WORKSPACE_ROOT / "traceability"
EXTERNALS_DIR = WORKSPACE_ROOT / "externals"

# Pattern to match GAP headers
GAP_HEADER_PATTERN = re.compile(r'^### (GAP-[A-Z0-9]+-\d+):\s*(.+)$')

# Pattern to extract source references
SOURCE_PATTERN = re.compile(r'\*\*Source\*\*:\s*(.+?)(?:\n\n|\n\*\*|$)', re.DOTALL)
DESCRIPTION_PATTERN = re.compile(r'\*\*Description\*\*:\s*(.+?)(?:\n\n|\n\*\*|$)', re.DOTALL)

# Keywords that suggest a gap might be resolved
RESOLUTION_KEYWORDS = [
    'implemented', 'added', 'fixed', 'resolved', 'supported',
    'available', 'enabled', 'complete', 'done'
]


def parse_gaps() -> dict:
    """Parse all GAP definitions from traceability files."""
    gaps = {}
    
    for md_file in TRACEABILITY_DIR.glob("*-gaps.md"):
        content = md_file.read_text()
        lines = content.split('\n')
        
        current_gap = None
        current_content = []
        
        for line in lines:
            match = GAP_HEADER_PATTERN.match(line)
            if match:
                # Save previous gap
                if current_gap:
                    gaps[current_gap['id']] = current_gap
                    current_gap['content'] = '\n'.join(current_content)
                
                # Start new gap
                current_gap = {
                    'id': match.group(1),
                    'title': match.group(2),
                    'file': md_file.name,
                    'content': ''
                }
                current_content = [line]
            elif current_gap:
                # Check for next section (## header means end of gap)
                if line.startswith('## ') or line.startswith('---'):
                    if current_content:
                        current_gap['content'] = '\n'.join(current_content)
                        gaps[current_gap['id']] = current_gap
                        current_gap = None
                        current_content = []
                else:
                    current_content.append(line)
        
        # Don't forget last gap
        if current_gap:
            current_gap['content'] = '\n'.join(current_content)
            gaps[current_gap['id']] = current_gap
    
    return gaps


def extract_search_terms(gap: dict) -> list[str]:
    """Extract searchable terms from gap definition."""
    terms = []
    content = gap['content']
    
    # Extract from title
    title_words = re.findall(r'[A-Z][a-z]+(?:[A-Z][a-z]+)*|\b[A-Z]{2,}\b', gap['title'])
    terms.extend(title_words)
    
    # Extract code references (backticked items)
    code_refs = re.findall(r'`([A-Za-z_][A-Za-z0-9_\.]+)`', content)
    terms.extend(code_refs)
    
    # Extract file paths from Source section
    source_match = SOURCE_PATTERN.search(content)
    if source_match:
        source_text = source_match.group(1)
        # Extract file names
        files = re.findall(r'([A-Za-z][A-Za-z0-9_-]+\.(swift|kt|java|js|ts))', source_text)
        terms.extend([f[0] for f in files])
    
    # Filter out common/short terms
    terms = [t for t in terms if len(t) >= 3 and t not in ['The', 'Not', 'API', 'the']]
    
    return list(set(terms))[:5]  # Limit to 5 unique terms


def check_gap_freshness(gap: dict) -> dict:
    """Check if a gap is still open or potentially resolved."""
    result = {
        'id': gap['id'],
        'title': gap['title'],
        'file': gap['file'],
        'status': 'UNKNOWN',
        'evidence': [],
        'search_terms': []
    }
    
    if not EXTERNALS_DIR.exists():
        result['status'] = 'ERROR'
        result['error'] = 'externals/ directory not found'
        return result
    
    terms = extract_search_terms(gap)
    result['search_terms'] = terms
    
    if not terms:
        result['status'] = 'NO_TERMS'
        result['note'] = 'Could not extract searchable terms from gap definition'
        return result
    
    # Search for each term
    found_count = 0
    for term in terms:
        try:
            cmd = ['grep', '-rl', '--include=*.swift', '--include=*.kt',
                   '--include=*.java', '--include=*.js', '--include=*.ts',
                   term, str(EXTERNALS_DIR)]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            
            if proc.returncode == 0 and proc.stdout.strip():
                matches = proc.stdout.strip().split('\n')[:3]
                result['evidence'].append({
                    'term': term,
                    'found': True,
                    'files': [os.path.relpath(m, WORKSPACE_ROOT) for m in matches]
                })
                found_count += 1
            else:
                result['evidence'].append({
                    'term': term,
                    'found': False
                })
        except subprocess.TimeoutExpired:
            result['evidence'].append({
                'term': term,
                'error': 'timeout'
            })
        except Exception as e:
            result['evidence'].append({
                'term': term,
                'error': str(e)
            })
    
    # Determine status based on evidence
    if found_count == 0:
        result['status'] = 'LIKELY_OPEN'
        result['confidence'] = 'high'
        result['reason'] = f'No matches for any of {len(terms)} search terms'
    elif found_count == len(terms):
        result['status'] = 'NEEDS_REVIEW'
        result['confidence'] = 'medium'
        result['reason'] = f'All {len(terms)} terms found in source - gap may be addressed'
    else:
        result['status'] = 'LIKELY_OPEN'
        result['confidence'] = 'low'
        result['reason'] = f'{found_count}/{len(terms)} terms found - partial implementation possible'
    
    return result


def print_results(results: list[dict], as_json: bool = False):
    """Print freshness check results."""
    if as_json:
        print(json.dumps(results, indent=2))
        return
    
    print(f"\n{'='*70}")
    print("GAP Freshness Check Results")
    print(f"{'='*70}\n")
    
    for r in results:
        status_icon = {
            'LIKELY_OPEN': '🔴',
            'NEEDS_REVIEW': '🟡',
            'NO_TERMS': '⚪',
            'ERROR': '❌',
            'UNKNOWN': '❓'
        }.get(r['status'], '❓')
        
        print(f"{status_icon} {r['id']}: {r['title'][:50]}...")
        print(f"   Status: {r['status']}")
        
        if r.get('reason'):
            print(f"   Reason: {r['reason']}")
        
        if r.get('search_terms'):
            print(f"   Terms: {', '.join(r['search_terms'][:3])}")
        
        if r.get('evidence'):
            for ev in r['evidence'][:2]:
                if ev.get('found'):
                    print(f"   ✓ `{ev['term']}` found in {len(ev.get('files', []))} files")
                elif ev.get('error'):
                    print(f"   ⚠ `{ev['term']}`: {ev['error']}")
                else:
                    print(f"   ✗ `{ev['term']}` not found")
        print()
    
    # Summary
    open_count = sum(1 for r in results if r['status'] == 'LIKELY_OPEN')
    review_count = sum(1 for r in results if r['status'] == 'NEEDS_REVIEW')
    
    print(f"{'='*70}")
    print(f"Summary: {len(results)} gaps checked")
    print(f"  🔴 Likely still open: {open_count}")
    print(f"  🟡 Needs review: {review_count}")
    print(f"  ⚪ Other: {len(results) - open_count - review_count}")
    print(f"{'='*70}")


def main():
    parser = argparse.ArgumentParser(description='Check if GAP issues are still open')
    parser.add_argument('--gap', type=str, help='Specific GAP ID to check (e.g., GAP-G7-001)')
    parser.add_argument('--sample', type=int, help='Random sample of N gaps')
    parser.add_argument('--all', action='store_true', help='Check all gaps (slow)')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--seed', type=int, help='Random seed for reproducibility')
    args = parser.parse_args()
    
    if args.seed is not None:
        random.seed(args.seed)
    
    gaps = parse_gaps()
    
    if not args.json:
        print(f"Found {len(gaps)} GAP definitions in traceability/")
    
    # Select gaps to check
    if args.gap:
        if args.gap not in gaps:
            print(f"Error: {args.gap} not found", file=sys.stderr)
            print(f"Available prefixes: {', '.join(set(g.split('-')[1] for g in gaps.keys()))}", file=sys.stderr)
            sys.exit(1)
        selected = [gaps[args.gap]]
    elif args.all:
        selected = list(gaps.values())
    elif args.sample:
        selected = random.sample(list(gaps.values()), min(args.sample, len(gaps)))
    else:
        # Default: sample 5
        selected = random.sample(list(gaps.values()), min(5, len(gaps)))
    
    if not args.json:
        print(f"Checking {len(selected)} gap(s)...")
    
    results = [check_gap_freshness(gap) for gap in selected]
    print_results(results, args.json)
    
    # Exit code: 0 if any need review (interesting finding)
    needs_review = sum(1 for r in results if r['status'] == 'NEEDS_REVIEW')
    sys.exit(0)


if __name__ == '__main__':
    main()
