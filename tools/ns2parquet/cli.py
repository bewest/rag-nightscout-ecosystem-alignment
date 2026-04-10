"""
cli.py — Command-line interface for ns2parquet.

Commands:
    convert     Convert a single patient's JSON directory to Parquet
    convert-all Convert all patients in a patients directory
    convert-odc Convert OpenAPS Data Commons patients to Parquet
    ingest      Fetch from live Nightscout API and convert to Parquet
    info        Show summary of existing Parquet files
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path


def _generate_opaque_id(source: str) -> str:
    """Generate a deterministic but opaque patient ID from a source string.

    Works with URLs, directory names, or any string. The same input always
    produces the same ID (enabling append/dedup across runs), but the
    source cannot be recovered from the ID.
    """
    normalized = source.strip().rstrip('/').lower()
    digest = hashlib.sha256(f'ns2parquet:{normalized}'.encode()).hexdigest()[:12]
    return f'ns-{digest}'


def cmd_convert(args):
    """Convert a single patient's Nightscout JSON directory to Parquet."""
    from .normalize import (
        normalize_entries, normalize_treatments,
        normalize_devicestatus, normalize_profiles,
        normalize_settings,
    )
    from .grid import build_grid
    from .writer import write_parquet
    from .schemas import (
        ENTRIES_SCHEMA, TREATMENTS_SCHEMA,
        DEVICESTATUS_SCHEMA, PROFILES_SCHEMA, SETTINGS_SCHEMA, GRID_SCHEMA,
    )

    data_dir = Path(args.input)
    if not data_dir.exists():
        print(f'ERROR: Input directory not found: {data_dir}', file=sys.stderr)
        return 1

    patient_id = args.patient_id
    if not patient_id:
        raw_name = data_dir.parent.name
        patient_id = _generate_opaque_id(raw_name) if args.opaque_ids else raw_name
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

    # Load site settings if available (from /api/v1/status.json)
    site_settings = None
    settings_path = data_dir / 'settings.json'
    if settings_path.exists():
        with open(settings_path) as f:
            status_doc = json.load(f)
        site_settings = status_doc.get('settings', status_doc)
        if verbose:
            site_units = site_settings.get('units', '?')
            enabled = site_settings.get('enable', [])
            has_pump = any(p in enabled for p in ['pump', 'iob', 'loop', 'openaps'])
            mode = 'AID/pump' if has_pump else 'MDI/CGM-only'
            print(f'  Site settings: units={site_units}, mode={mode}')

    # Cross-check: if site_settings has units, verify profile units agree
    if site_settings:
        site_units = (site_settings.get('units') or '').lower().replace('/', '')
        profile_data = collections['profile']
        if isinstance(profile_data, list) and profile_data:
            store = profile_data[0].get('store', {})
            for pname, pval in store.items():
                prof_units = (pval.get('units') or '').lower().replace('/', '')
                if prof_units and site_units and prof_units != site_units:
                    print(f'  ⚠ Unit mismatch: site={site_units}, '
                          f'profile "{pname}"={prof_units}')

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

    # Normalize site settings if available
    if site_settings:
        settings_df = normalize_settings(
            {'settings': site_settings}, patient_id)
        if verbose:
            print(f'  settings: {len(settings_df)} rows '
                  f'(units={site_settings.get("units", "?")}, '
                  f'mode={settings_df["data_mode"].iloc[0] if len(settings_df) else "?"})')
        write_parquet(settings_df, output, 'settings', SETTINGS_SCHEMA,
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
    subset = args.subset  # training, verification, both, raw, or None (auto-detect)

    # Parse --patients filter
    patient_filter = None
    if getattr(args, 'patients', None):
        patient_filter = set(p.strip() for p in args.patients.split(',') if p.strip())

    # Find patient directories (contain ns_url.env or JSON files)
    patient_dirs = sorted([
        d for d in patients_dir.iterdir()
        if d.is_dir() and not d.name.startswith('.')
    ])

    # Apply patient filter
    if patient_filter:
        patient_dirs = [d for d in patient_dirs if d.name in patient_filter]
        if verbose:
            print(f'Filtered to {len(patient_dirs)} patients: {", ".join(sorted(patient_filter))}')

    # Determine subsets to process
    if subset == 'both':
        subsets_to_run = ['training', 'verification']
    elif subset:
        subsets_to_run = [subset]
    else:
        subsets_to_run = [None]  # auto-detect

    if verbose:
        print(f'Found {len(patient_dirs)} patient directories in {patients_dir}')
        print(f'Output: {output}/')
        if subset == 'both':
            print(f'Subsets: training + verification')
        elif subset:
            print(f'Subset: {subset}')
        print()

    t0 = time.time()
    success = 0
    failed = 0

    for current_subset in subsets_to_run:
        if len(subsets_to_run) > 1 and verbose:
            print(f'{"━" * 60}')
            print(f'  Subset: {current_subset}')
            print(f'{"━" * 60}')
            print()

        # For "both" mode, output to subdirectories
        if subset == 'both':
            current_output = str(Path(output) / current_subset)
        else:
            current_output = output

        for pdir in patient_dirs:
            raw_name = pdir.name
            patient_id = _generate_opaque_id(raw_name) if args.opaque_ids else raw_name

            # Determine data subdirectory
            if current_subset:
                data_dir = pdir / current_subset
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
            conv_args.output = current_output
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
        if subset == 'both':
            print(f'  Output: {output}/training/ + {output}/verification/')
        else:
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

    # Generate or use patient ID
    if args.patient_id:
        patient_id = args.patient_id
    else:
        patient_id = _generate_opaque_id(base_url)

    if verbose:
        print(f'Ingesting {args.days} days from {base_url}')
        print(f'Patient ID: {patient_id}'
              f'{" (auto-generated)" if not args.patient_id else ""}')

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=args.days)

    # Use ns_fetch functions
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from cgmencode.ns_fetch import fetch_entries, fetch_treatments, fetch_devicestatus, fetch_json

    now_ms = int(now.timestamp() * 1000)
    start_ms = int(start.timestamp() * 1000)

    if verbose:
        print(f'Fetching site status/settings...')
    try:
        status = fetch_json(f'{base_url}/api/v1/status.json')
    except Exception as e:
        if verbose:
            print(f'  WARNING: Could not fetch status: {e}')
        status = None

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

        # Save site settings if available
        if status:
            with open(Path(tmpdir) / 'settings.json', 'w') as f:
                json.dump(status, f)
            if verbose:
                settings = status.get('settings', {})
                site_units = settings.get('units', '?')
                enabled = settings.get('enable', [])
                has_pump = any(p in enabled for p in ['pump', 'iob', 'loop', 'openaps'])
                mode = 'AID/pump' if has_pump else 'MDI/CGM-only'
                print(f'  Site: units={site_units}, mode={mode}, '
                      f'plugins={len(enabled)}')

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


def cmd_merge(args):
    """Merge parquet files from multiple directories into one."""
    import pandas as pd
    from .writer import write_parquet, _dedup_key

    verbose = not args.quiet
    output = args.output
    sources = args.sources

    if verbose:
        print(f'Merging {len(sources)} sources → {output}/')
        print()

    t0 = time.time()
    # Discover all collections across all sources
    collections = set()
    for src in sources:
        src_path = Path(src)
        if not src_path.exists():
            print(f'  WARNING: {src} does not exist, skipping', file=sys.stderr)
            continue
        for pf in src_path.glob('*.parquet'):
            collections.add(pf.stem)

    if not collections:
        print('ERROR: No parquet files found in any source directory', file=sys.stderr)
        return 1

    for collection in sorted(collections):
        frames = []
        for src in sources:
            pf = Path(src) / f'{collection}.parquet'
            if pf.exists():
                df = pd.read_parquet(pf)
                frames.append(df)
                if verbose:
                    print(f'  {collection}: {len(df):,} rows from {src}')

        if not frames:
            continue

        merged = pd.concat(frames, ignore_index=True)

        # Deduplicate
        dedup_cols = _dedup_key(collection)
        valid_cols = [c for c in dedup_cols if c in merged.columns]
        before = len(merged)
        if valid_cols:
            merged = merged.drop_duplicates(subset=valid_cols, keep='last')

        if verbose:
            deduped = before - len(merged)
            dedup_str = f' ({deduped:,} duplicates removed)' if deduped else ''
            print(f'  → {collection}: {len(merged):,} rows merged{dedup_str}')

        write_parquet(merged, output, collection, append=False, verbose=False)

    elapsed = time.time() - t0
    if verbose:
        print()
        print(f'{"═" * 60}')
        print(f'  Merged {len(collections)} collections in {elapsed:.1f}s')
        print(f'  Output: {output}/')
        print(f'{"═" * 60}')

    return 0


def cmd_info(args):
    """Show summary of existing Parquet files."""
    import pandas as pd
    from .writer import parquet_info

    info = parquet_info(args.input)
    if not info:
        print(f'No parquet files found in {args.input}')
        return 1

    detail = getattr(args, 'detail', False)
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

        # Per-patient detail
        if detail and stats['num_patients'] > 0:
            pf = Path(args.input) / f'{collection}.parquet'
            try:
                # Pick timestamp column for date range
                ts_col = None
                for candidate in ['time', 'date', 'created_at']:
                    if candidate in pd.read_parquet(pf, columns=None).columns:
                        ts_col = candidate
                        break

                df = pd.read_parquet(pf)
                for pid in sorted(stats['patients']):
                    pdf = df[df['patient_id'] == pid]
                    row_info = f'{len(pdf):>8,} rows'
                    if ts_col and ts_col in pdf.columns:
                        ts_min = pdf[ts_col].min()
                        ts_max = pdf[ts_col].max()
                        if pd.notna(ts_min) and pd.notna(ts_max):
                            days = (ts_max - ts_min).total_seconds() / 86400
                            row_info += f'  {str(ts_min.date())} → {str(ts_max.date())} ({days:.0f}d)'
                    print(f'  {"":20s}    {pid:>12s}: {row_info}')
            except Exception:
                pass  # graceful fallback if detail fails

    print(f'{"─" * 70}')
    print(f'  {"TOTAL":20s}  {total_rows:>10,} rows  '
          f'{total_size / (1024*1024):>8.1f} MB')
    print(f'{"═" * 70}')

    return 0


def cmd_convert_odc(args):
    """Convert OpenAPS Data Commons patients to Parquet.

    Discovers ODC patient directories (numeric IDs), converts AAPS-native
    JSON to Nightscout-shaped dicts, then builds grids+Parquet using the
    standard pipeline.
    """
    import tempfile
    from .odc_loader import discover_odc_patients, write_odc_as_nightscout
    from .grid import build_grid
    from .normalize import (
        normalize_entries, normalize_treatments,
        normalize_devicestatus, normalize_profiles,
    )
    from .writer import write_parquet
    from .schemas import (
        ENTRIES_SCHEMA, TREATMENTS_SCHEMA,
        DEVICESTATUS_SCHEMA, PROFILES_SCHEMA, GRID_SCHEMA,
    )

    odc_dir = Path(args.odc_dir)
    if not odc_dir.exists():
        print(f'ERROR: ODC directory not found: {odc_dir}', file=sys.stderr)
        return 1

    verbose = not args.quiet
    output = args.output

    # Discover patients
    all_patients = discover_odc_patients(str(odc_dir))
    if not all_patients:
        print(f'ERROR: No patient directories found in {odc_dir}', file=sys.stderr)
        return 1

    # Filter
    patient_filter = None
    if getattr(args, 'patients', None):
        patient_filter = set(p.strip() for p in args.patients.split(',') if p.strip())
        all_patients = [(pid, pp) for pid, pp in all_patients if pid in patient_filter]

    if verbose:
        print(f'Found {len(all_patients)} ODC patient(s) in {odc_dir}')
        print(f'Output: {output}/')
        print()

    t0 = time.time()
    success = 0
    failed = 0

    for odc_pid, patient_path in all_patients:
        patient_id = (_generate_opaque_id(f'odc-{odc_pid}')
                      if args.opaque_ids else f'odc-{odc_pid}')
        if verbose:
            print(f'── ODC Patient {odc_pid} → {patient_id} ──')

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                ns_dir = str(Path(tmpdir) / 'data')
                ok = write_odc_as_nightscout(patient_path, ns_dir,
                                             verbose=verbose)
                if not ok:
                    if verbose:
                        print(f'  SKIP: insufficient data')
                    failed += 1
                    continue

                # Load converted JSON for raw Parquet tables
                import json as _json
                entries_list = _json.load(open(Path(ns_dir) / 'entries.json'))
                treatments_list = _json.load(open(Path(ns_dir) / 'treatments.json'))
                ds_list = _json.load(open(Path(ns_dir) / 'devicestatus.json'))
                profile_list = _json.load(open(Path(ns_dir) / 'profile.json'))

                # Normalize raw tables
                entries_df = normalize_entries(entries_list, patient_id)
                treatments_df = normalize_treatments(treatments_list, patient_id)
                devicestatus_df = normalize_devicestatus(ds_list, patient_id)
                profiles_df = normalize_profiles(profile_list, patient_id)

                # Write raw Parquet tables
                for name, df, schema in [
                    ('entries', entries_df, ENTRIES_SCHEMA),
                    ('treatments', treatments_df, TREATMENTS_SCHEMA),
                    ('devicestatus', devicestatus_df, DEVICESTATUS_SCHEMA),
                    ('profiles', profiles_df, PROFILES_SCHEMA),
                ]:
                    if df is not None and len(df) > 0:
                        df['patient_id'] = patient_id
                        write_parquet(df, output, name,
                                      schema=schema, append=True)

                # Build research grid
                if not args.skip_grid:
                    grid = build_grid(ns_dir, patient_id)
                    write_parquet(grid.reset_index(drop=True),
                                 output, 'grid',
                                 schema=GRID_SCHEMA, append=True)
                    if verbose:
                        print(f'  Grid: {len(grid)} rows × {grid.shape[1]} cols')

            success += 1
        except Exception as e:
            print(f'  ERROR {odc_pid}: {e}', file=sys.stderr)
            failed += 1

        if verbose:
            print()

    elapsed = time.time() - t0
    if verbose:
        print(f'{"═" * 60}')
        print(f'  Converted {success}/{success + failed} ODC patients '
              f'in {elapsed:.1f}s')
        print(f'  Output: {output}/')
        print(f'{"═" * 60}')

    return 0 if failed == 0 else 1


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
        help='Patient identifier (default: parent directory name, or hash with --opaque-ids)')
    p_conv.add_argument('--opaque-ids', action='store_true', default=False,
        help='Hash directory names into opaque IDs (e.g., ns-a1b2c3d4e5f6)')
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
    p_all.add_argument('--subset', '-s', choices=['training', 'verification', 'raw', 'both'],
        help='Data subset to use (default: auto-detect). "both" converts training + verification to separate subdirs.')
    p_all.add_argument('--patients',
        help='Comma-separated list of patient IDs to include (default: all)')
    p_all.add_argument('--output', '-o', default='output',
        help='Output directory for Parquet files')
    p_all.add_argument('--opaque-ids', action='store_true', default=False,
        help='Hash directory names into opaque IDs (e.g., ns-a1b2c3d4e5f6)')
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
    p_ing.add_argument('--patient-id', '-p',
        help='Patient identifier (default: auto-generated opaque hash of URL)')
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
    p_info.add_argument('--detail', action='store_true',
        help='Show per-patient row counts and date ranges')

    # merge
    p_merge = subparsers.add_parser('merge',
        help='Merge parquet files from multiple directories')
    p_merge.add_argument('sources', nargs='+',
        help='Source directories containing Parquet files')
    p_merge.add_argument('--output', '-o', required=True,
        help='Output directory for merged Parquet files')
    p_merge.add_argument('--quiet', '-q', action='store_true')

    # convert-odc
    p_odc = subparsers.add_parser('convert-odc',
        help='Convert OpenAPS Data Commons patients to Parquet')
    p_odc.add_argument('--odc-dir', '-d', required=True,
        help='Root directory of ODC dataset (contains numeric patient dirs)')
    p_odc.add_argument('--patients',
        help='Comma-separated list of ODC patient IDs to include (default: all)')
    p_odc.add_argument('--output', '-o', default='output',
        help='Output directory for Parquet files')
    p_odc.add_argument('--opaque-ids', action='store_true', default=False,
        help='Hash patient IDs into opaque IDs')
    p_odc.add_argument('--skip-grid', action='store_true',
        help='Skip building the research grid')
    p_odc.add_argument('--quiet', '-q', action='store_true')

    args = parser.parse_args()

    if args.command == 'convert':
        return cmd_convert(args)
    elif args.command == 'convert-all':
        return cmd_convert_all(args)
    elif args.command == 'ingest':
        return cmd_ingest(args)
    elif args.command == 'info':
        return cmd_info(args)
    elif args.command == 'merge':
        return cmd_merge(args)
    elif args.command == 'convert-odc':
        return cmd_convert_odc(args)
    else:
        parser.print_help()
        return 1
