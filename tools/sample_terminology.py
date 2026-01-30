#!/usr/bin/env python3
"""
Sample terminology matrix entries and verify against source code.

Usage:
    python tools/sample_terminology.py --sample-size 10
    python tools/sample_terminology.py --sample-size 20 --json
    python tools/sample_terminology.py --verify-all
"""

import argparse
import json
import os
import random
import re
import subprocess
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).parent.parent
TERMINOLOGY_FILE = WORKSPACE_ROOT / "mapping/cross-project/terminology-matrix.md"
EXTERNALS_DIR = WORKSPACE_ROOT / "externals"

# Patterns to extract verifiable terms from tables
TABLE_ROW_PATTERN = re.compile(r'^\|\s*([^|]+)\s*\|(.+)\|$')
FIELD_REFERENCE_PATTERN = re.compile(r'`([A-Za-z_][A-Za-z0-9_\.]*)`')

# Source file extensions by project
PROJECT_EXTENSIONS = {
    'Loop': ['swift'],
    'AAPS': ['kt', 'java'],
    'Trio': ['swift'],
    'oref0': ['js'],
    'xDrip': ['java', 'kt'],
    'DiaBLE': ['swift'],
    'Nightscout': ['js'],
}


def extract_terms(content: str) -> list[dict]:
    """Extract verifiable terms from terminology matrix."""
    terms = []
    lines = content.split('\n')
    current_section = None
    
    for i, line in enumerate(lines):
        # Track section headers
        if line.startswith('##'):
            current_section = line.strip('# ').strip()
            continue
        
        # Skip header rows and dividers
        if '---' in line or not line.strip().startswith('|'):
            continue
        
        match = TABLE_ROW_PATTERN.match(line.strip())
        if not match:
            continue
        
        first_col = match.group(1).strip()
        rest = match.group(2)
        
        # Skip table headers (usually bold or contain "Field", "System", etc.)
        if first_col.startswith('**') or first_col in ['Field', 'System', 'Concept', 'Term', 'Aspect']:
            continue
        
        # Extract field references from the row
        fields = FIELD_REFERENCE_PATTERN.findall(rest)
        if not fields:
            continue
        
        # Parse project columns
        cols = [c.strip() for c in rest.split('|')]
        
        terms.append({
            'term': first_col.strip('`*'),
            'section': current_section,
            'fields': fields,
            'raw_cols': cols,
            'line': i + 1
        })
    
    return terms


def verify_term(term: dict) -> dict:
    """Verify a term exists in source code."""
    result = {
        'term': term['term'],
        'section': term['section'],
        'line': term['line'],
        'fields_checked': [],
        'found': 0,
        'not_found': 0,
        'verified': False
    }
    
    if not EXTERNALS_DIR.exists():
        result['error'] = 'externals/ directory not found'
        return result
    
    # Try to find each field reference in source
    for field in term['fields'][:3]:  # Limit to first 3 fields
        if len(field) < 3 or field in ['N/A', 'No', 'Yes', 'None', 'Full', 'Read', 'Same']:
            continue
        
        field_result = {'field': field, 'found_in': []}
        
        # Search in externals
        try:
            cmd = ['grep', '-rl', '--include=*.swift', '--include=*.kt', 
                   '--include=*.java', '--include=*.js', '--include=*.ts',
                   field, str(EXTERNALS_DIR)]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if proc.returncode == 0 and proc.stdout.strip():
                matches = proc.stdout.strip().split('\n')[:3]  # Limit matches
                for m in matches:
                    rel = os.path.relpath(m, WORKSPACE_ROOT)
                    field_result['found_in'].append(rel)
                result['found'] += 1
            else:
                result['not_found'] += 1
        except subprocess.TimeoutExpired:
            field_result['error'] = 'timeout'
            result['not_found'] += 1
        except Exception as e:
            field_result['error'] = str(e)
            result['not_found'] += 1
        
        result['fields_checked'].append(field_result)
    
    # Consider verified if at least one field found
    result['verified'] = result['found'] > 0
    return result


def sample_terms(terms: list[dict], sample_size: int) -> list[dict]:
    """Random sample of terms."""
    if sample_size >= len(terms):
        return terms
    return random.sample(terms, sample_size)


def print_results(results: list[dict], as_json: bool = False):
    """Print verification results."""
    if as_json:
        print(json.dumps(results, indent=2))
        return
    
    verified = sum(1 for r in results if r['verified'])
    total = len(results)
    
    print(f"\n{'='*60}")
    print(f"Terminology Matrix Sample Verification")
    print(f"{'='*60}\n")
    
    for r in results:
        status = "✓" if r['verified'] else "✗"
        print(f"{status} {r['term']}")
        print(f"  Section: {r['section']}")
        print(f"  Line: {r['line']}")
        
        for fc in r['fields_checked']:
            if fc.get('found_in'):
                print(f"    ✓ `{fc['field']}` found in:")
                for loc in fc['found_in'][:2]:
                    print(f"      - {loc}")
            elif fc.get('error'):
                print(f"    ⚠ `{fc['field']}`: {fc['error']}")
            else:
                print(f"    ✗ `{fc['field']}` not found in externals/")
        print()
    
    print(f"{'='*60}")
    pct = (verified / total * 100) if total > 0 else 0
    print(f"Accuracy: {pct:.1f}% ({verified}/{total} terms verified)")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description='Sample terminology matrix for verification')
    parser.add_argument('--sample-size', type=int, default=10, help='Number of terms to sample')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--verify-all', action='store_true', help='Verify all terms (slow)')
    parser.add_argument('--seed', type=int, help='Random seed for reproducibility')
    args = parser.parse_args()
    
    if args.seed is not None:
        random.seed(args.seed)
    
    if not TERMINOLOGY_FILE.exists():
        print(f"Error: {TERMINOLOGY_FILE} not found", file=sys.stderr)
        sys.exit(1)
    
    content = TERMINOLOGY_FILE.read_text()
    terms = extract_terms(content)
    
    if not args.json:
        print(f"Found {len(terms)} verifiable terms in terminology matrix")
    
    if args.verify_all:
        selected = terms
    else:
        selected = sample_terms(terms, args.sample_size)
    
    if not args.json:
        print(f"Verifying {len(selected)} terms...")
    
    results = [verify_term(t) for t in selected]
    print_results(results, args.json)
    
    # Exit code: 0 if >80% verified, 1 otherwise
    verified = sum(1 for r in results if r['verified'])
    accuracy = verified / len(results) if results else 0
    sys.exit(0 if accuracy >= 0.8 else 1)


if __name__ == '__main__':
    main()
