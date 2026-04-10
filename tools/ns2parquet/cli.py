"""
cli.py — Command-line interface for ns2parquet.

Commands:
    convert     Convert a single patient's JSON directory to Parquet
    convert-all Convert all patients in a patients directory
    ingest      Fetch from live Nightscout API and convert to Parquet
    info        Show summary of existing Parquet files
"""

import argparse
import json
import sys
import time
from pathlib import Path


def cmd_convert(args):
    """Convert a single patient's Nightscout JSON directory to Parquet."""
    from .normalize import (
        normalize_entries, normalize_treatments,
        normalize_devicestatus, normalize_profiles,
    )
    from .grid import build_grid
    from .writer import write_parquet
    from .schemas import (
        ENTRIES_SCHEMA, TREATMENTS_SCHEMA,
        DEVICESTATUS_SCHEMA, PROFILES_SCHEMA, GRID_SCHEMA,
    )

    data_dir = Path(args.input)
    if not data_dir.exists():
        print(f'ERROR: Input directory not found: {data_dir}', file=sys.stderr)
        return 1

    patient_id = args.patient_id or data_dir.parent.name
    verbose = not args.quiet
    output = args.output

    if verbose:
        print(f'Converting {data_dir} (patient: {patient_id}) → {output}/')

    t0 = time.time()

    # Load raw JSON
    collections = {}
    for name in ['entries', 'treatments', 'devicestatus', 'profile']:
        fpath = data_dir / f'{name}.json'
        if fpath.exists():
            with open(fpath) as f:
                collections[name] = json.load(f)
        else:
            collections[name] = [] if name != 'profile' else {}

    # Normalize each collection
    if verbose:
        print(f'\n── Normalizing collections ──')

    entries_df = normalize_entries(collections['entries'], patient_id)
    if verbose:
        print(f'  entries: {len(entries_df)} rows')
    write_parquet(entries_df, output, 'entries', ENTRIES_SCHEMA,
                  append=args.append, verbose=verbose)

    treatments_df = normalize_treatments(collections['treatments'], patient_id)
    if verbose:
        print(f'  treatments: {len(treatments_df)} rows')
    write_parquet(treatments_df, output, 'treatments', TREATMENTS_SCHEMA,
                  append=args.append, verbose=verbose)

    ds_df = normalize_devicestatus(collections['devicestatus'], patient_id)
    if verbose:
        print(f'  devicestatus: {len(ds_df)} rows')
    write_parquet(ds_df, output, 'devicestatus', DEVICESTATUS_SCHEMA,
                  append=args.append, verbose=verbose)

    profiles_df = normalize_profiles(collections['profile'], patient_id)
    if verbose:
        print(f'  profiles: {len(profiles_df)} rows')
    write_parquet(profiles_df, output, 'profiles', PROFILES_SCHEMA,
                  append=args.append, verbose=verbose)

    # Build research grid
    if not args.skip_grid:
        if verbose:
            print(f'\n── Building research grid ──')
        grid_df = build_grid(str(data_dir), patient_id, verbose=verbose)
        if grid_df is not None:
            write_parquet(grid_df, output, 'grid', None,
                          append=args.append, verbose=verbose)

    elapsed = time.time() - t0
    if verbose:
        print(f'\n{"═" * 60}')
        print(f'  Done in {elapsed:.1f}s → {output}/')
        print(f'{"═" * 60}')

    return 0


def cmd_convert_all(args):
    """Convert all patients in a patients directory to Parquet."""
    patients_dir = Path(args.patients_dir)
    if not patients_dir.exists():
        print(f'ERROR: Patients directory not found: {patients_dir}', file=sys.stderr)
        return 1

    verbose = not args.quiet
    output = args.output
    subset = args.subset  # training, verification, raw, or None (auto-detect)

    # Find patient directories (contain ns_url.env or JSON files)
    patient_dirs = sorted([
        d for d in patients_dir.iterdir()
        if d.is_dir() and not d.name.startswith('.')
    ])

    if verbose:
        print(f'Found {len(patient_dirs)} patient directories in {patients_dir}')
        print(f'Output: {output}/')
        if subset:
            print(f'Subset: {subset}')
        print()

    t0 = time.time()
    success = 0
    failed = 0

    for pdir in patient_dirs:
        patient_id = pdir.name

        # Determine data subdirectory
        if subset:
            data_dir = pdir / subset
        else:
            # Auto-detect: prefer training, then raw, then root
            for sub in ['training', 'raw', '']:
                candidate = pdir / sub if sub else pdir
                if (candidate / 'entries.json').exists():
                    data_dir = candidate
                    break
            else:
                if verbose:
                    print(f'  SKIP {patient_id}: no JSON files found')
                failed += 1
                continue

        if not (data_dir / 'entries.json').exists():
            if verbose:
                print(f'  SKIP {patient_id}: no entries.json in {data_dir}')
            failed += 1
            continue

        if verbose:
            print(f'── Patient {patient_id} ({data_dir.relative_to(patients_dir)}) ──')

        # Create a fake args for cmd_convert
        class ConvertArgs:
            pass
        conv_args = ConvertArgs()
        conv_args.input = str(data_dir)
        conv_args.patient_id = patient_id
        conv_args.output = output
        conv_args.append = True  # always append in batch mode
        conv_args.quiet = args.quiet
        conv_args.skip_grid = args.skip_grid

        try:
            rc = cmd_convert(conv_args)
            if rc == 0:
                success += 1
            else:
                failed += 1
        except Exception as e:
            print(f'  ERROR {patient_id}: {e}', file=sys.stderr)
            failed += 1

        if verbose:
            print()

    elapsed = time.time() - t0
    if verbose:
        print(f'{"═" * 60}')
        print(f'  Converted {success}/{success + failed} patients in {elapsed:.1f}s')
        print(f'  Output: {output}/')
        print(f'{"═" * 60}')

    return 0 if failed == 0 else 1


def cmd_ingest(args):
    """Fetch from live Nightscout API and convert to Parquet."""
    # Reuse ns_fetch patterns
    import urllib.request
    import urllib.parse
    from datetime import datetime, timedelta, timezone

    verbose = not args.quiet
    output = args.output
    patient_id = args.patient_id

    # Resolve URL
    if args.env:
        with open(args.env) as f:
            for line in f:
                line = line.strip()
                if line.startswith('NS_URL='):
                    base_url = line.split('=', 1)[1].strip().strip('"').strip("'").rstrip('/')
                    break
            else:
                print(f'ERROR: NS_URL not found in {args.env}', file=sys.stderr)
                return 1
    else:
        base_url = args.url.rstrip('/')

    if verbose:
        print(f'Ingesting {args.days} days from {base_url}')

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=args.days)

    # Use ns_fetch functions
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from cgmencode.ns_fetch import fetch_entries, fetch_treatments, fetch_devicestatus, fetch_json

    now_ms = int(now.timestamp() * 1000)
    start_ms = int(start.timestamp() * 1000)

    if verbose:
        print(f'Fetching entries...')
    entries = fetch_entries(base_url, start_ms, now_ms, verbose=verbose)

    if verbose:
        print(f'Fetching treatments...')
    treatments = fetch_treatments(base_url, start, now, verbose=verbose)

    if verbose:
        print(f'Fetching devicestatus...')
    devicestatus = fetch_devicestatus(base_url, start, now, verbose=verbose)

    if verbose:
        print(f'Fetching profile...')
    profile = fetch_json(f'{base_url}/api/v1/profile.json')

    # Write temp JSON then convert
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        for name, data in [('entries', entries), ('treatments', treatments),
                           ('devicestatus', devicestatus), ('profile', profile)]:
            with open(Path(tmpdir) / f'{name}.json', 'w') as f:
                json.dump(data, f)

        class ConvertArgs:
            pass
        conv_args = ConvertArgs()
        conv_args.input = tmpdir
        conv_args.patient_id = patient_id
        conv_args.output = output
        conv_args.append = True
        conv_args.quiet = args.quiet
        conv_args.skip_grid = args.skip_grid

        return cmd_convert(conv_args)


def cmd_info(args):
    """Show summary of existing Parquet files."""
    from .writer import parquet_info

    info = parquet_info(args.input)
    if not info:
        print(f'No parquet files found in {args.input}')
        return 1

    total_rows = 0
    total_size = 0

    print(f'Parquet files in {args.input}/')
    print(f'{"═" * 70}')
    for collection, stats in info.items():
        total_rows += stats['rows']
        total_size += stats['size_bytes']
        patients_str = ', '.join(stats['patients'][:10])
        if len(stats['patients']) > 10:
            patients_str += f'... (+{len(stats["patients"]) - 10} more)'
        print(f'  {collection:20s}  {stats["rows"]:>10,} rows  '
              f'{stats["size_mb"]:>8.1f} MB  '
              f'{stats["num_patients"]} patients')
        if patients_str:
            print(f'  {"":20s}  patients: {patients_str}')
    print(f'{"─" * 70}')
    print(f'  {"TOTAL":20s}  {total_rows:>10,} rows  '
          f'{total_size / (1024*1024):>8.1f} MB')
    print(f'{"═" * 70}')

    return 0


def main():
    parser = argparse.ArgumentParser(
        prog='ns2parquet',
        description='Convert Nightscout data to Parquet for research and analytics',
    )
    subparsers = parser.add_subparsers(dest='command', help='Command')

    # convert
    p_conv = subparsers.add_parser('convert',
        help='Convert a single patient JSON directory to Parquet')
    p_conv.add_argument('--input', '-i', required=True,
        help='Input directory with entries.json, treatments.json, etc.')
    p_conv.add_argument('--patient-id', '-p',
        help='Patient identifier (default: parent directory name)')
    p_conv.add_argument('--output', '-o', default='output',
        help='Output directory for Parquet files (default: output/)')
    p_conv.add_argument('--append', action='store_true', default=False,
        help='Append to existing Parquet files (default: overwrite)')
    p_conv.add_argument('--skip-grid', action='store_true',
        help='Skip building the research grid')
    p_conv.add_argument('--quiet', '-q', action='store_true')

    # convert-all
    p_all = subparsers.add_parser('convert-all',
        help='Convert all patients in a directory')
    p_all.add_argument('--patients-dir', '-d', required=True,
        help='Directory containing patient subdirectories')
    p_all.add_argument('--subset', '-s', choices=['training', 'verification', 'raw'],
        help='Data subset to use (default: auto-detect)')
    p_all.add_argument('--output', '-o', default='output',
        help='Output directory for Parquet files')
    p_all.add_argument('--skip-grid', action='store_true',
        help='Skip building the research grid')
    p_all.add_argument('--quiet', '-q', action='store_true')

    # ingest
    p_ing = subparsers.add_parser('ingest',
        help='Fetch from live Nightscout API and convert to Parquet')
    url_group = p_ing.add_mutually_exclusive_group(required=True)
    url_group.add_argument('--url', help='Nightscout site URL')
    url_group.add_argument('--env', help='Path to env file with NS_URL=...')
    p_ing.add_argument('--days', type=int, default=90,
        help='Days of history to fetch (default: 90)')
    p_ing.add_argument('--patient-id', '-p', required=True,
        help='Patient identifier for this site')
    p_ing.add_argument('--output', '-o', default='output',
        help='Output directory for Parquet files')
    p_ing.add_argument('--skip-grid', action='store_true',
        help='Skip building the research grid')
    p_ing.add_argument('--quiet', '-q', action='store_true')

    # info
    p_info = subparsers.add_parser('info',
        help='Show summary of Parquet files')
    p_info.add_argument('--input', '-i', default='output',
        help='Directory containing Parquet files')

    args = parser.parse_args()

    if args.command == 'convert':
        return cmd_convert(args)
    elif args.command == 'convert-all':
        return cmd_convert_all(args)
    elif args.command == 'ingest':
        return cmd_ingest(args)
    elif args.command == 'info':
        return cmd_info(args)
    else:
        parser.print_help()
        return 1
