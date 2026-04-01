#!/usr/bin/env python3
"""
ns_patients.py — Multi-patient Nightscout data collection orchestrator.

Manages per-patient env files, fetches data, splits train/verify, and
validates that each patient has sufficient data for training.

Directory layout:
    externals/ns-data/patients/
    ├── a/
    │   ├── ns_url.env          # NS_URL=https://...
    │   ├── raw/                # Full fetched data
    │   │   ├── entries.json
    │   │   ├── treatments.json
    │   │   ├── devicestatus.json
    │   │   ├── profile.json
    │   │   └── manifest.json
    │   ├── training/           # 90% of days
    │   └── verification/       # 10% of days
    ├── b/ ...
    └── j/

Subcommands:
    init     Create/validate env file for a patient
    fetch    Fetch data for one or all patients
    split    Split raw → training/verification for one or all patients
    status   Show data status for all patients
    validate Check data quality and sufficiency

Usage:
    # Set up a patient URL
    python3 -m tools.cgmencode.ns_patients init a --url https://patient-a.example.com

    # Fetch all configured patients (180 days)
    python3 -m tools.cgmencode.ns_patients fetch --all --days 180

    # Split all patients
    python3 -m tools.cgmencode.ns_patients split --all

    # Check status
    python3 -m tools.cgmencode.ns_patients status

    # Validate data quality
    python3 -m tools.cgmencode.ns_patients validate --all
"""

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Relative import of sibling modules when run as -m tools.cgmencode.ns_patients
try:
    from .ns_fetch import load_ns_url, fetch_entries, fetch_treatments, \
        fetch_devicestatus, fetch_json
    from .ns_split import split_records
except ImportError:
    # Direct execution fallback
    from ns_fetch import load_ns_url, fetch_entries, fetch_treatments, \
        fetch_devicestatus, fetch_json
    from ns_split import split_records

PATIENTS_DIR = Path('externals/ns-data/patients')
PATIENT_IDS = list('abcdefghij')
MIN_DAYS = 90
RECOMMENDED_DAYS = 180


def get_patient_dir(patient_id):
    return PATIENTS_DIR / patient_id


def read_env(patient_id):
    """Read NS_URL from patient env file. Returns URL or None."""
    env_path = get_patient_dir(patient_id) / 'ns_url.env'
    if not env_path.exists():
        return None
    try:
        return load_ns_url(str(env_path))
    except (ValueError, FileNotFoundError):
        return None


def test_ns_url(url):
    """Quick connectivity test — fetch 1 entry."""
    try:
        data = fetch_json(f'{url}/api/v1/entries.json', {'count': 1})
        if isinstance(data, list) and len(data) > 0:
            newest = data[0].get('dateString', 'unknown')
            return True, f'OK (newest entry: {newest})'
        return False, 'API returned empty entries'
    except Exception as e:
        return False, f'Connection failed: {e}'


# ── init ──────────────────────────────────────────────────────────────────

def cmd_init(args):
    """Create or update env file for a patient."""
    pid = args.patient
    pdir = get_patient_dir(pid)
    pdir.mkdir(parents=True, exist_ok=True)

    env_path = pdir / 'ns_url.env'

    if args.url:
        url = args.url.rstrip('/')
        # Test connectivity
        print(f'Testing {url}...')
        ok, msg = test_ns_url(url)
        if ok:
            print(f'  ✓ {msg}')
        else:
            print(f'  ✗ {msg}')
            if not args.force:
                print('  Use --force to save anyway')
                return 1

        with open(env_path, 'w') as f:
            f.write(f'NS_URL={url}\n')
        print(f'  Saved: {env_path}')
        return 0

    # No URL provided — check existing
    if env_path.exists():
        url = read_env(pid)
        print(f'Patient {pid}: {url}')
        ok, msg = test_ns_url(url)
        print(f'  {("✓" if ok else "✗")} {msg}')
    else:
        print(f'Patient {pid}: no env file')
        print(f'  Create with: python3 -m tools.cgmencode.ns_patients init {pid} --url <URL>')
    return 0


# ── fetch ─────────────────────────────────────────────────────────────────

def fetch_patient(pid, days, skip_ds=False, verbose=True):
    """Fetch data for a single patient."""
    url = read_env(pid)
    if not url:
        print(f'  Patient {pid}: no NS_URL configured — skipping')
        return False

    raw_dir = get_patient_dir(pid) / 'raw'
    raw_dir.mkdir(parents=True, exist_ok=True)

    from datetime import timedelta
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    now_ms = int(now.timestamp() * 1000)
    start_ms = int(start.timestamp() * 1000)

    if verbose:
        print(f'  Patient {pid}: fetching {days} days from {url}')

    try:
        # Entries
        entries = fetch_entries(url, start_ms, now_ms, verbose=verbose)
        with open(raw_dir / 'entries.json', 'w') as f:
            json.dump(entries, f)

        # Treatments
        treatments = fetch_treatments(url, start, now, verbose=verbose)
        with open(raw_dir / 'treatments.json', 'w') as f:
            json.dump(treatments, f)

        # DeviceStatus
        if not skip_ds:
            devicestatus = fetch_devicestatus(url, start, now, verbose=verbose)
            with open(raw_dir / 'devicestatus.json', 'w') as f:
                json.dump(devicestatus, f)
        else:
            devicestatus = []

        # Profile
        profile = fetch_json(f'{url}/api/v1/profile.json')
        with open(raw_dir / 'profile.json', 'w') as f:
            json.dump(profile, f)

        # Manifest
        manifest = {
            'patient': pid,
            'capturedAt': now.isoformat(),
            'source': url,
            'requestedDays': days,
            'counts': {
                'entries': len(entries),
                'treatments': len(treatments),
                'devicestatus': len(devicestatus),
            },
        }
        with open(raw_dir / 'manifest.json', 'w') as f:
            json.dump(manifest, f, indent=2)

        if verbose:
            total = len(entries) + len(treatments) + len(devicestatus)
            print(f'  → {total:,} records ({len(entries)} entries, '
                  f'{len(treatments)} treatments, {len(devicestatus)} devicestatus)')
        return True

    except Exception as e:
        print(f'  ✗ Patient {pid} fetch failed: {e}')
        return False


def cmd_fetch(args):
    """Fetch data for patients."""
    patients = PATIENT_IDS if args.all else [args.patient]
    days = args.days

    ok_count = 0
    for pid in patients:
        success = fetch_patient(pid, days, skip_ds=args.skip_devicestatus,
                                verbose=not args.quiet)
        if success:
            ok_count += 1
        print()

    print(f'Fetched {ok_count}/{len(patients)} patients')
    return 0 if ok_count > 0 else 1


# ── split ─────────────────────────────────────────────────────────────────

def split_patient(pid, every_n=10, verbose=True):
    """Split raw → training/verification for one patient."""
    pdir = get_patient_dir(pid)
    raw_dir = pdir / 'raw'

    if not raw_dir.exists():
        if verbose:
            print(f'  Patient {pid}: no raw data — run fetch first')
        return False

    train_dir = pdir / 'training'
    verify_dir = pdir / 'verification'
    train_dir.mkdir(exist_ok=True)
    verify_dir.mkdir(exist_ok=True)

    import shutil
    collections = ['entries.json', 'treatments.json', 'devicestatus.json']
    total_stats = {}

    for filename in collections:
        filepath = raw_dir / filename
        if not filepath.exists():
            continue

        collection = filename.replace('.json', '')
        with open(filepath) as f:
            records = json.load(f)

        if not isinstance(records, list):
            continue

        train_recs, verify_recs, day_stats = split_records(
            records, collection, every_n)

        total_stats[collection] = {
            'total': len(records),
            'training': len(train_recs),
            'verification': len(verify_recs),
        }

        with open(train_dir / filename, 'w') as f:
            json.dump(train_recs, f)
        with open(verify_dir / filename, 'w') as f:
            json.dump(verify_recs, f)

    # Copy profile to both
    profile_path = raw_dir / 'profile.json'
    if profile_path.exists():
        shutil.copy2(profile_path, train_dir / 'profile.json')
        shutil.copy2(profile_path, verify_dir / 'profile.json')

    if verbose and total_stats:
        e = total_stats.get('entries', {})
        print(f'  Patient {pid}: {e.get("total", 0):,} entries → '
              f'{e.get("training", 0):,} train / {e.get("verification", 0):,} verify')

    return bool(total_stats)


def cmd_split(args):
    """Split raw data into train/verify."""
    patients = PATIENT_IDS if args.all else [args.patient]
    every_n = args.every

    ok_count = 0
    for pid in patients:
        if split_patient(pid, every_n, verbose=not args.quiet):
            ok_count += 1

    print(f'Split {ok_count}/{len(patients)} patients (every {every_n}th day held out)')
    return 0


# ── status ────────────────────────────────────────────────────────────────

def cmd_status(args):
    """Show data collection status for all patients."""
    print(f'{"Patient":>8}  {"URL":>5}  {"Raw":>8}  {"Entries":>8}  '
          f'{"Days":>5}  {"Train":>7}  {"Verify":>7}  {"Status"}')
    print(f'{"─" * 8}  {"─" * 5}  {"─" * 8}  {"─" * 8}  '
          f'{"─" * 5}  {"─" * 7}  {"─" * 7}  {"─" * 12}')

    for pid in PATIENT_IDS:
        pdir = get_patient_dir(pid)
        url = read_env(pid)
        has_url = '✓' if url else '·'

        raw_dir = pdir / 'raw'
        has_raw = '·'
        entry_count = 0
        day_count = 0

        if (raw_dir / 'entries.json').exists():
            has_raw = '✓'
            try:
                with open(raw_dir / 'entries.json') as f:
                    entries = json.load(f)
                entry_count = len(entries)
                # Count unique days
                days = set()
                for e in entries:
                    ds = e.get('dateString', '')[:10]
                    if ds:
                        days.add(ds)
                day_count = len(days)
            except (json.JSONDecodeError, KeyError):
                pass

        train_count = 0
        verify_count = 0
        train_path = pdir / 'training' / 'entries.json'
        verify_path = pdir / 'verification' / 'entries.json'
        if train_path.exists():
            try:
                with open(train_path) as f:
                    train_count = len(json.load(f))
            except (json.JSONDecodeError, ValueError):
                pass
        if verify_path.exists():
            try:
                with open(verify_path) as f:
                    verify_count = len(json.load(f))
            except (json.JSONDecodeError, ValueError):
                pass

        # Status
        if not url:
            status = 'needs URL'
        elif entry_count == 0:
            status = 'needs fetch'
        elif day_count < MIN_DAYS:
            status = f'low ({day_count}d)'
        elif train_count == 0:
            status = 'needs split'
        else:
            status = '✓ ready'

        print(f'{pid:>8}  {has_url:>5}  {has_raw:>8}  {entry_count:>8,}  '
              f'{day_count:>5}  {train_count:>7,}  {verify_count:>7,}  {status}')

    return 0


# ── validate ──────────────────────────────────────────────────────────────

def validate_patient(pid, verbose=True):
    """Check data quality for one patient."""
    pdir = get_patient_dir(pid)
    issues = []

    # Check raw data exists
    raw_dir = pdir / 'raw'
    for f in ['entries.json', 'treatments.json', 'devicestatus.json', 'profile.json']:
        if not (raw_dir / f).exists():
            issues.append(f'missing raw/{f}')

    if issues:
        if verbose:
            print(f'  Patient {pid}: {", ".join(issues)}')
        return issues

    # Check entry coverage
    with open(raw_dir / 'entries.json') as f:
        entries = json.load(f)

    if len(entries) == 0:
        issues.append('no CGM entries')
        if verbose:
            print(f'  Patient {pid}: no CGM entries')
        return issues

    days = set()
    for e in entries:
        ds = e.get('dateString', '')[:10]
        if ds:
            days.add(ds)

    n_days = len(days)
    if n_days < MIN_DAYS:
        issues.append(f'only {n_days} days (need {MIN_DAYS}+)')

    # Check CGM density (expect ~288 readings/day at 5-min intervals)
    expected_per_day = 288
    actual_per_day = len(entries) / max(n_days, 1)
    coverage_pct = actual_per_day / expected_per_day * 100
    if coverage_pct < 70:
        issues.append(f'low CGM coverage ({coverage_pct:.0f}%, expect 70%+)')

    # Check devicestatus has IOB
    with open(raw_dir / 'devicestatus.json') as f:
        ds_records = json.load(f)

    iob_count = sum(1 for d in ds_records
                    if d.get('loop', {}).get('iob', {}).get('iob') is not None)
    if iob_count < len(entries) * 0.3:
        issues.append(f'low IOB coverage ({iob_count}/{len(entries)} entries)')

    # Check profile has ISF/CR
    with open(raw_dir / 'profile.json') as f:
        profiles = json.load(f)
    if isinstance(profiles, list) and len(profiles) > 0:
        store = profiles[0].get('store', {})
        default = store.get('Default', store.get(list(store.keys())[0], {})) if store else {}
        if not default.get('sens'):
            issues.append('profile missing ISF (sens)')
        if not default.get('carbratio'):
            issues.append('profile missing CR (carbratio)')
    else:
        issues.append('no profile data')

    # Check train/verify split exists
    if not (pdir / 'training' / 'entries.json').exists():
        issues.append('not split yet (run split)')

    if verbose:
        if issues:
            print(f'  Patient {pid}: ⚠ {"; ".join(issues)}')
        else:
            print(f'  Patient {pid}: ✓ {n_days} days, {len(entries):,} entries, '
                  f'{coverage_pct:.0f}% coverage, IOB {iob_count:,}')

    return issues


def cmd_validate(args):
    """Validate data quality for patients."""
    patients = PATIENT_IDS if args.all else [args.patient]
    all_ok = True

    for pid in patients:
        issues = validate_patient(pid, verbose=True)
        if issues:
            all_ok = False

    return 0 if all_ok else 1


# ── main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Multi-patient Nightscout data collection',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Set up patient URLs
  %(prog)s init a --url https://patient-a-ns.example.com
  %(prog)s init b --url https://patient-b-ns.example.com

  # Fetch all configured patients
  %(prog)s fetch --all --days 180

  # Split all into train/verify
  %(prog)s split --all

  # Check status
  %(prog)s status

  # Validate data quality
  %(prog)s validate --all
""")
    sub = parser.add_subparsers(dest='command', required=True)

    # init
    p_init = sub.add_parser('init', help='Create/validate patient env file')
    p_init.add_argument('patient', choices=PATIENT_IDS, help='Patient ID (a-j)')
    p_init.add_argument('--url', help='Nightscout URL')
    p_init.add_argument('--force', action='store_true', help='Save even if URL test fails')

    # fetch
    p_fetch = sub.add_parser('fetch', help='Fetch NS data for patient(s)')
    fetch_target = p_fetch.add_mutually_exclusive_group(required=True)
    fetch_target.add_argument('patient', nargs='?', choices=PATIENT_IDS,
                              help='Patient ID')
    fetch_target.add_argument('--all', action='store_true',
                              help='Fetch all configured patients')
    p_fetch.add_argument('--days', type=int, default=180,
                         help='Days of history (default: 180)')
    p_fetch.add_argument('--skip-devicestatus', action='store_true')
    p_fetch.add_argument('--quiet', '-q', action='store_true')

    # split
    p_split = sub.add_parser('split', help='Split raw → train/verify')
    split_target = p_split.add_mutually_exclusive_group(required=True)
    split_target.add_argument('patient', nargs='?', choices=PATIENT_IDS)
    split_target.add_argument('--all', action='store_true')
    p_split.add_argument('--every', type=int, default=10,
                         help='Hold out every Nth day (default: 10)')
    p_split.add_argument('--quiet', '-q', action='store_true')

    # status
    sub.add_parser('status', help='Show all patient data status')

    # validate
    p_val = sub.add_parser('validate', help='Validate data quality')
    val_target = p_val.add_mutually_exclusive_group(required=True)
    val_target.add_argument('patient', nargs='?', choices=PATIENT_IDS)
    val_target.add_argument('--all', action='store_true')

    args = parser.parse_args()

    # Ensure base directory exists
    PATIENTS_DIR.mkdir(parents=True, exist_ok=True)

    cmd = {
        'init': cmd_init,
        'fetch': cmd_fetch,
        'split': cmd_split,
        'status': cmd_status,
        'validate': cmd_validate,
    }
    return cmd[args.command](args)


if __name__ == '__main__':
    sys.exit(main() or 0)
