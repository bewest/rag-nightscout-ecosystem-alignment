#!/usr/bin/env python3
"""
ns_split.py — Split Nightscout JSON data into training/verification by day.

Reads a raw NS data directory (entries.json, treatments.json, devicestatus.json,
profile.json) and splits into two directories where every Nth day is held out
for verification.  Profile is copied to both (it applies globally).

The split is deterministic: day number from epoch mod N decides the bucket.
This means the same data always produces the same split, and newly fetched
data for the same dates lands in the same bucket.

Usage:
    # Split existing 90-day fixtures (default 10% verification)
    python3 -m tools.cgmencode.ns_split \\
        --input ../t1pal-mobile-workspace/externals/logs/ns-fixtures/90-day-history \\
        --output externals/ns-data

    # Custom hold-out ratio (every 5th day = 20%)
    python3 -m tools.cgmencode.ns_split --input /path/to/raw --output /path/to/split --every 5

    # Then use for hindcast verification:
    python3 -m tools.cgmencode.hindcast forecast \\
        --data externals/ns-data/verification \\
        --checkpoint externals/experiments/cond_transfer.pth \\
        --model conditioned --scan 5
"""

import argparse
import json
import os
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def parse_date(record, collection):
    """Extract a datetime from a record, handling different NS collections."""
    try:
        if collection == 'entries':
            # Entries use millisecond 'date' field
            if 'date' in record:
                return datetime.fromtimestamp(record['date'] / 1000, tz=timezone.utc)
            if 'dateString' in record:
                return datetime.fromisoformat(record['dateString'].replace('Z', '+00:00'))
        elif collection in ('treatments', 'devicestatus'):
            # Treatments/devicestatus use ISO 'created_at'
            if 'created_at' in record:
                ts = record['created_at'].replace('Z', '+00:00')
                return datetime.fromisoformat(ts)
        # Fallback: try common fields
        for field in ('dateString', 'created_at', 'sysTime'):
            if field in record:
                ts = record[field].replace('Z', '+00:00')
                return datetime.fromisoformat(ts)
    except (ValueError, TypeError, KeyError):
        pass
    return None


def day_number(dt):
    """Deterministic day number from epoch (UTC date only)."""
    return (dt.year * 10000 + dt.month * 100 + dt.day)


def split_records(records, collection, every_n):
    """Split records into (training, verification) lists by day."""
    training = []
    verification = []
    day_stats = defaultdict(lambda: {'train': 0, 'verify': 0})

    for record in records:
        dt = parse_date(record, collection)
        if dt is None:
            training.append(record)  # unparseable → training
            continue

        day_key = dt.strftime('%Y-%m-%d')
        # Deterministic: day-of-year mod N == 0 → verification
        day_ord = dt.timetuple().tm_yday + dt.year * 366
        if day_ord % every_n == 0:
            verification.append(record)
            day_stats[day_key]['verify'] += 1
        else:
            training.append(record)
            day_stats[day_key]['train'] += 1

    return training, verification, day_stats


def main():
    parser = argparse.ArgumentParser(
        description='Split Nightscout data into training/verification by day')
    parser.add_argument('--input', '-i', required=True,
                        help='Input directory with entries.json, treatments.json, etc.')
    parser.add_argument('--output', '-o', required=True,
                        help='Output base directory (creates training/ and verification/ subdirs)')
    parser.add_argument('--every', type=int, default=10,
                        help='Hold out every Nth day for verification (default: 10 = 10%%)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show split statistics without writing files')
    parser.add_argument('--quiet', '-q', action='store_true')
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    train_dir = output_dir / 'training'
    verify_dir = output_dir / 'verification'

    # Validate input
    collections = ['entries.json', 'treatments.json', 'devicestatus.json']
    missing = [f for f in collections if not (input_dir / f).exists()]
    if missing:
        print(f'WARNING: Missing files in {input_dir}: {", ".join(missing)}')
        print(f'         Will skip missing collections.')

    if not args.dry_run:
        train_dir.mkdir(parents=True, exist_ok=True)
        verify_dir.mkdir(parents=True, exist_ok=True)

    total_stats = {}

    for filename in collections:
        filepath = input_dir / filename
        if not filepath.exists():
            continue

        collection = filename.replace('.json', '')
        if not args.quiet:
            print(f'\nSplitting {filename}...')

        with open(filepath) as f:
            records = json.load(f)

        if not isinstance(records, list):
            print(f'  Skipping {filename}: not a JSON array')
            continue

        train_recs, verify_recs, day_stats = split_records(
            records, collection, args.every)

        total_stats[collection] = {
            'total': len(records),
            'training': len(train_recs),
            'verification': len(verify_recs),
            'days_total': len(day_stats),
            'days_verify': sum(1 for d in day_stats.values() if d['verify'] > 0),
        }

        if not args.quiet:
            s = total_stats[collection]
            pct = 100 * s['verification'] / s['total'] if s['total'] else 0
            print(f'  Total: {s["total"]:,} records across {s["days_total"]} days')
            print(f'  Training:     {s["training"]:>7,} records '
                  f'({s["days_total"] - s["days_verify"]} days)')
            print(f'  Verification: {s["verification"]:>7,} records '
                  f'({s["days_verify"]} days, {pct:.1f}%)')

        if not args.dry_run:
            with open(train_dir / filename, 'w') as f:
                json.dump(train_recs, f)
            with open(verify_dir / filename, 'w') as f:
                json.dump(verify_recs, f)

    # Copy profile.json to both (it's global, not day-specific)
    profile_path = input_dir / 'profile.json'
    if profile_path.exists():
        if not args.dry_run:
            shutil.copy2(profile_path, train_dir / 'profile.json')
            shutil.copy2(profile_path, verify_dir / 'profile.json')
        if not args.quiet:
            print(f'\nprofile.json → copied to both splits')

    # Write split manifest
    if not args.dry_run:
        manifest = {
            'source': str(input_dir),
            'split_at': datetime.now(timezone.utc).isoformat(),
            'every_n_days': args.every,
            'hold_out_pct': round(100 / args.every, 1),
            'collections': total_stats,
        }
        with open(output_dir / 'split-manifest.json', 'w') as f:
            json.dump(manifest, f, indent=2)

    # Summary
    if not args.quiet:
        print(f'\n{"═" * 60}')
        print(f'  Split complete: every {args.every}th day → verification')
        if not args.dry_run:
            print(f'  Training:     {train_dir}/')
            print(f'  Verification: {verify_dir}/')
            print(f'  Manifest:     {output_dir}/split-manifest.json')
        print(f'{"═" * 60}')

    # Show verification day dates for transparency
    if not args.quiet and total_stats.get('entries'):
        filepath = input_dir / 'entries.json'
        if filepath.exists():
            with open(filepath) as f:
                records = json.load(f)
            verify_days = set()
            for rec in records:
                dt = parse_date(rec, 'entries')
                if dt:
                    day_ord = dt.timetuple().tm_yday + dt.year * 366
                    if day_ord % args.every == 0:
                        verify_days.add(dt.strftime('%Y-%m-%d'))
            if verify_days:
                days_sorted = sorted(verify_days)
                print(f'\n  Verification days ({len(days_sorted)}):')
                for d in days_sorted:
                    print(f'    {d}')


if __name__ == '__main__':
    main()
