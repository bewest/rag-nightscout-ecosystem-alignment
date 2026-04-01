#!/usr/bin/env python3
"""
ns_fetch.py — Fetch Nightscout data into a hindcast-ready directory.

Fetches entries, treatments, devicestatus, and profile from a Nightscout
API into JSON files that build_nightscout_grid() can consume directly.

Usage:
    # Fetch 60 days from NS_URL in env file
    python3 -m tools.cgmencode.ns_fetch \\
        --env ../t1pal-mobile-workspace/externals/ns_url.env \\
        --days 60 --output externals/ns-data/live-recent

    # Fetch with explicit URL
    python3 -m tools.cgmencode.ns_fetch \\
        --url https://your-ns.example.com \\
        --days 30 --output /tmp/ns-data

    # Then split and evaluate:
    python3 -m tools.cgmencode.ns_split -i externals/ns-data/live-recent -o externals/ns-data
    python3 -m tools.cgmencode.hindcast forecast \\
        --data externals/ns-data/verification --scan 5 ...
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path


def load_ns_url(env_path):
    """Parse NS_URL from a bash-style env file."""
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith('NS_URL='):
                url = line.split('=', 1)[1].strip().strip('"').strip("'")
                return url.rstrip('/')
    raise ValueError(f'NS_URL not found in {env_path}')


def fetch_json(url, params=None):
    """Fetch JSON from a URL with query parameters."""
    if params:
        qs = urllib.parse.urlencode(params)
        url = f'{url}?{qs}'
    req = urllib.request.Request(url, headers={'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_entries(base_url, start_ms, end_ms, verbose=False):
    """Fetch CGM entries in 7-day windows (NS has a 10K record limit)."""
    all_entries = []
    window_ms = 7 * 86400 * 1000  # 7 days

    cursor = end_ms
    while cursor > start_ms:
        win_start = max(start_ms, cursor - window_ms)
        if verbose:
            d1 = datetime.fromtimestamp(win_start / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
            d2 = datetime.fromtimestamp(cursor / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
            print(f'  entries {d1} → {d2}...', end='', flush=True)

        params = {
            'find[date][$gte]': int(win_start),
            'find[date][$lt]': int(cursor),
            'count': 10000,
        }
        chunk = fetch_json(f'{base_url}/api/v1/entries.json', params)
        if verbose:
            print(f' {len(chunk)} records')
        all_entries.extend(chunk)
        cursor -= window_ms
        time.sleep(0.5)  # be polite

    # Deduplicate by _id and sort
    seen = set()
    unique = []
    for e in all_entries:
        eid = e.get('_id', id(e))
        if eid not in seen:
            seen.add(eid)
            unique.append(e)
    unique.sort(key=lambda x: x.get('date', 0), reverse=True)
    return unique


def fetch_treatments(base_url, start_dt, end_dt, verbose=False):
    """Fetch treatments in 7-day windows."""
    all_treatments = []
    window = timedelta(days=7)

    cursor = end_dt
    while cursor > start_dt:
        win_start = max(start_dt, cursor - window)
        if verbose:
            print(f'  treatments {win_start.strftime("%Y-%m-%d")} → '
                  f'{cursor.strftime("%Y-%m-%d")}...', end='', flush=True)

        params = {
            'find[created_at][$gte]': win_start.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
            'find[created_at][$lt]': cursor.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
            'count': 10000,
        }
        chunk = fetch_json(f'{base_url}/api/v1/treatments.json', params)
        if verbose:
            print(f' {len(chunk)} records')
        all_treatments.extend(chunk)
        cursor -= window
        time.sleep(0.5)

    seen = set()
    unique = []
    for t in all_treatments:
        tid = t.get('_id', id(t))
        if tid not in seen:
            seen.add(tid)
            unique.append(t)
    unique.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return unique


def fetch_devicestatus(base_url, start_dt, end_dt, verbose=False):
    """Fetch devicestatus in 7-day windows."""
    all_ds = []
    window = timedelta(days=7)

    cursor = end_dt
    while cursor > start_dt:
        win_start = max(start_dt, cursor - window)
        if verbose:
            print(f'  devicestatus {win_start.strftime("%Y-%m-%d")} → '
                  f'{cursor.strftime("%Y-%m-%d")}...', end='', flush=True)

        params = {
            'find[created_at][$gte]': win_start.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
            'find[created_at][$lt]': cursor.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
            'count': 10000,
        }
        chunk = fetch_json(f'{base_url}/api/v1/devicestatus.json', params)
        if verbose:
            print(f' {len(chunk)} records')
        all_ds.extend(chunk)
        cursor -= window
        time.sleep(0.5)

    seen = set()
    unique = []
    for d in all_ds:
        did = d.get('_id', id(d))
        if did not in seen:
            seen.add(did)
            unique.append(d)
    unique.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return unique


def main():
    parser = argparse.ArgumentParser(
        description='Fetch Nightscout data for hindcast evaluation')
    url_group = parser.add_mutually_exclusive_group(required=True)
    url_group.add_argument('--url', help='Nightscout site URL')
    url_group.add_argument('--env', help='Path to env file with NS_URL=...')
    parser.add_argument('--output', '-o', required=True,
                        help='Output directory for JSON files')
    parser.add_argument('--days', type=int, default=60,
                        help='Days of history to fetch (default: 60)')
    parser.add_argument('--skip-devicestatus', action='store_true',
                        help='Skip devicestatus (largest download, needed for IOB/COB)')
    parser.add_argument('--quiet', '-q', action='store_true')
    args = parser.parse_args()

    # Resolve URL
    if args.env:
        base_url = load_ns_url(args.env)
    else:
        base_url = args.url.rstrip('/')

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    verbose = not args.quiet

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=args.days)
    now_ms = int(now.timestamp() * 1000)
    start_ms = int(start.timestamp() * 1000)

    if verbose:
        print(f'Fetching {args.days} days from {base_url}')
        print(f'  Range: {start.strftime("%Y-%m-%d")} → {now.strftime("%Y-%m-%d")}')
        print()

    # 1. Entries
    if verbose:
        print('Fetching entries (CGM readings)...')
    entries = fetch_entries(base_url, start_ms, now_ms, verbose=verbose)
    with open(output_dir / 'entries.json', 'w') as f:
        json.dump(entries, f)
    if verbose:
        print(f'  → {len(entries):,} entries\n')

    # 2. Treatments
    if verbose:
        print('Fetching treatments (bolus, carbs, temp basal)...')
    treatments = fetch_treatments(base_url, start, now, verbose=verbose)
    with open(output_dir / 'treatments.json', 'w') as f:
        json.dump(treatments, f)
    if verbose:
        print(f'  → {len(treatments):,} treatments\n')

    # 3. DeviceStatus (largest — skip if requested)
    if not args.skip_devicestatus:
        if verbose:
            print('Fetching devicestatus (IOB, COB, Loop state)...')
        devicestatus = fetch_devicestatus(base_url, start, now, verbose=verbose)
        with open(output_dir / 'devicestatus.json', 'w') as f:
            json.dump(devicestatus, f)
        if verbose:
            print(f'  → {len(devicestatus):,} devicestatus records\n')
    else:
        if verbose:
            print('Skipping devicestatus (--skip-devicestatus)\n')

    # 4. Profile (single fetch, not date-ranged)
    if verbose:
        print('Fetching profile...')
    profile = fetch_json(f'{base_url}/api/v1/profile.json')
    with open(output_dir / 'profile.json', 'w') as f:
        json.dump(profile, f)
    if verbose:
        print(f'  → {len(profile) if isinstance(profile, list) else 1} profile(s)\n')

    # Manifest
    manifest = {
        'capturedAt': now.isoformat(),
        'source': base_url,
        'requestedDays': args.days,
        'dateRange': {
            'start': start.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'end': now.strftime('%Y-%m-%dT%H:%M:%SZ'),
        },
        'counts': {
            'entries': len(entries),
            'treatments': len(treatments),
        },
    }
    if not args.skip_devicestatus:
        manifest['counts']['devicestatus'] = len(devicestatus)
    with open(output_dir / 'manifest.json', 'w') as f:
        json.dump(manifest, f, indent=2)

    if verbose:
        total = len(entries) + len(treatments)
        if not args.skip_devicestatus:
            total += len(devicestatus)
        print(f'{"═" * 60}')
        print(f'  Fetch complete: {total:,} records → {output_dir}/')
        sizes = []
        for fn in ['entries.json', 'treatments.json', 'devicestatus.json', 'profile.json']:
            p = output_dir / fn
            if p.exists():
                sz = p.stat().st_size
                sizes.append((fn, sz))
                print(f'    {fn:<25} {sz / 1024:>8.1f} KB')
        print(f'    {"TOTAL":<25} {sum(s for _, s in sizes) / 1024:>8.1f} KB')
        print(f'{"═" * 60}')


if __name__ == '__main__':
    main()
