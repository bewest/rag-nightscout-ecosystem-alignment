#!/usr/bin/env python3
"""Batch-ingest Nightscout sites from a CSV list into opaque-ID parquet.

Reads a two-column CSV (formula_type, nightscout_url) like the DynISF
Analysis spreadsheet, preprocesses each URL (strips tokens), and calls
the ns2parquet ingest pipeline per site.

Usage:
    python3 -m tools.ns2parquet.batch_ingest \
        --csv ~/Downloads/sites.csv \
        --days 180 \
        --output externals/ns-parquet-dynisf

The CSV file is never copied into the repository.  Patient IDs are
deterministic SHA-256 hashes of the clean base URL (token-free), so
repeated runs produce the same IDs and deduplicate cleanly.

After ingestion, a ``manifest.json`` is written with per-patient metadata
(opaque_id, days of data retrieved, row counts, formula annotation).
"""

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Tuple, Optional


def parse_csv(csv_path: str) -> List[Tuple[str, str]]:
    """Read the two-column CSV and return [(annotation, url), …].

    Handles missing headers, trailing whitespace, and blank lines.
    """
    rows: list = []
    with open(csv_path, newline='') as f:
        reader = csv.reader(f)
        for line in reader:
            if len(line) < 2:
                continue
            annotation = line[0].strip()
            url = line[1].strip()
            if not url or not url.startswith('http'):
                continue
            rows.append((annotation, url))
    return rows


def batch_ingest(csv_path: str, days: int, output: str,
                 quiet: bool = False, skip_grid: bool = False,
                 dry_run: bool = False) -> dict:
    """Ingest every site in *csv_path* into *output* directory.

    Returns a manifest dict with per-patient metadata.
    """
    from .ns_fetch import parse_ns_url
    from .cli import _generate_opaque_id, cmd_ingest

    rows = parse_csv(csv_path)
    if not rows:
        print(f'ERROR: No valid rows in {csv_path}', file=sys.stderr)
        return {}

    if not quiet:
        print(f'Batch ingest: {len(rows)} sites, {days} days each')
        print(f'Output: {output}/')
        print()

    Path(output).mkdir(parents=True, exist_ok=True)

    manifest_patients = []
    results = {'ok': 0, 'fail': 0, 'skip': 0}

    for idx, (annotation, raw_url) in enumerate(rows, 1):
        base_url, token = parse_ns_url(raw_url)
        opaque_id = _generate_opaque_id(base_url)

        if not quiet:
            print(f'[{idx}/{len(rows)}] {opaque_id}  '
                  f'(annotation={annotation!r})')

        if dry_run:
            manifest_patients.append({
                'patient_id': opaque_id,
                'annotation': annotation,
                'base_url_host': '(redacted)',
                'has_token': token is not None,
            })
            results['skip'] += 1
            continue

        # Build an argparse.Namespace that cmd_ingest expects
        ingest_args = argparse.Namespace(
            url=base_url,
            env=None,
            token=token,
            days=days,
            patient_id=opaque_id,
            output=output,
            skip_grid=skip_grid,
            quiet=quiet,
        )

        try:
            rc = cmd_ingest(ingest_args)
            if rc and rc != 0:
                raise RuntimeError(f'ingest returned {rc}')
            results['ok'] += 1
            status = 'ok'
        except Exception as e:
            if not quiet:
                print(f'  ERROR: {e}')
            results['fail'] += 1
            status = f'error: {e}'

        manifest_patients.append({
            'patient_id': opaque_id,
            'annotation': annotation,
            'status': status,
        })

        # Be polite to remote servers
        time.sleep(1.0)

    # Write manifest
    manifest = {
        'built': datetime.now(timezone.utc).isoformat(),
        'source': f'batch_ingest({Path(csv_path).name})',
        'days_requested': days,
        'patients': manifest_patients,
        'totals': results,
    }
    manifest_path = Path(output) / 'manifest.json'
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    if not quiet:
        print()
        print(f'Done: {results["ok"]} ok, {results["fail"]} failed, '
              f'{results["skip"]} skipped')
        print(f'Manifest: {manifest_path}')

    return manifest


# ── Chronological split & merge ──────────────────────────────────────

# Collections and the timestamp column used for chronological splitting.
_TIME_COL = {
    'grid': 'time',
    'entries': 'date',
    'treatments': 'created_at',
    'devicestatus': 'created_at',
    'profiles': None,           # profiles are atemporal — go to training only
    'settings': None,           # site-level — training only
}

# Minimum days of data needed for a patient to warrant a verification split.
_MIN_DAYS_FOR_SPLIT = 30


def split_chronological(input_dir: str, output_dir: str,
                        train_frac: float = 0.8,
                        quiet: bool = False) -> dict:
    """Split flat ingested parquet into training/ and verification/ subsets.

    For each patient in each collection, rows are sorted by time and the
    first *train_frac* go to ``output_dir/training/``, the remainder to
    ``output_dir/verification/``.  Patients with fewer than
    ``_MIN_DAYS_FOR_SPLIT`` days are placed entirely in training.

    Returns per-patient summary dict.
    """
    import pandas as pd
    from .writer import write_parquet

    input_path = Path(input_dir)
    train_out = str(Path(output_dir) / 'training')
    verif_out = str(Path(output_dir) / 'verification')
    Path(train_out).mkdir(parents=True, exist_ok=True)
    Path(verif_out).mkdir(parents=True, exist_ok=True)

    patient_summary = {}

    for pf in sorted(input_path.glob('*.parquet')):
        collection = pf.stem
        time_col = _TIME_COL.get(collection)
        df = pd.read_parquet(pf)

        if 'patient_id' not in df.columns or time_col is None:
            # Atemporal / no patient_id — training only
            write_parquet(df, train_out, collection, append=True,
                          verbose=False)
            if not quiet:
                print(f'  {collection}: {len(df):,} rows → training (no split)')
            continue

        train_frames = []
        verif_frames = []

        for pid, pat in df.groupby('patient_id'):
            pat = pat.sort_values(time_col)

            # Compute duration
            try:
                t_min = pd.Timestamp(pat[time_col].min())
                t_max = pd.Timestamp(pat[time_col].max())
                days = (t_max - t_min).total_seconds() / 86400
            except Exception:
                days = 0

            if days < _MIN_DAYS_FOR_SPLIT:
                train_frames.append(pat)
                if not quiet:
                    print(f'  {collection}/{pid}: {len(pat):,} rows, '
                          f'{days:.0f}d → training only (< {_MIN_DAYS_FOR_SPLIT}d)')
                patient_summary.setdefault(pid, {})['days'] = days
                patient_summary[pid]['split'] = 'training-only'
                continue

            split_idx = int(len(pat) * train_frac)
            train_frames.append(pat.iloc[:split_idx])
            verif_frames.append(pat.iloc[split_idx:])

            if not quiet:
                split_date = pat.iloc[split_idx][time_col]
                print(f'  {collection}/{pid}: {len(pat):,} rows, '
                      f'{days:.0f}d → {split_idx} train / '
                      f'{len(pat)-split_idx} verif '
                      f'(split at {str(split_date)[:10]})')
            patient_summary.setdefault(pid, {})['days'] = days
            patient_summary[pid]['split'] = f'{train_frac:.0%}/{1-train_frac:.0%}'

        if train_frames:
            write_parquet(pd.concat(train_frames, ignore_index=True),
                          train_out, collection, append=True, verbose=False)
        if verif_frames:
            write_parquet(pd.concat(verif_frames, ignore_index=True),
                          verif_out, collection, append=True, verbose=False)

    return patient_summary


def merge_into_terrarium(staging_dir: str,
                         terrarium_dir: str = 'externals/ns-parquet',
                         quiet: bool = False) -> None:
    """Merge split staging data into the existing terrarium.

    Reads ``staging_dir/training/`` and ``staging_dir/verification/``,
    appends into ``terrarium_dir/training/`` and
    ``terrarium_dir/verification/`` respectively, with deduplication.
    """
    import pandas as pd
    from .writer import write_parquet, _dedup_key

    for subset in ('training', 'verification'):
        src = Path(staging_dir) / subset
        dst = Path(terrarium_dir) / subset
        if not src.exists():
            continue
        dst.mkdir(parents=True, exist_ok=True)

        for pf in sorted(src.glob('*.parquet')):
            collection = pf.stem
            new_df = pd.read_parquet(pf)
            dst_pf = dst / f'{collection}.parquet'

            if dst_pf.exists():
                existing = pd.read_parquet(dst_pf)
                merged = pd.concat([existing, new_df], ignore_index=True)
                # Dedup
                dedup_cols = _dedup_key(collection)
                valid = [c for c in dedup_cols if c in merged.columns]
                if valid:
                    before = len(merged)
                    merged = merged.drop_duplicates(subset=valid, keep='last')
                    deduped = before - len(merged)
                else:
                    deduped = 0
                if not quiet:
                    extra = f' ({deduped} dupes removed)' if deduped else ''
                    print(f'  {subset}/{collection}: '
                          f'{len(existing):,} + {len(new_df):,} '
                          f'→ {len(merged):,}{extra}')
                write_parquet(merged, str(dst), collection,
                              append=False, verbose=False)
            else:
                if not quiet:
                    print(f'  {subset}/{collection}: {len(new_df):,} rows (new)')
                write_parquet(new_df, str(dst), collection,
                              append=False, verbose=False)


def main():
    parser = argparse.ArgumentParser(
        description='Batch-ingest Nightscout sites from a CSV file')
    sub = parser.add_subparsers(dest='command')

    # ── ingest ──
    p_ing = sub.add_parser('ingest',
        help='Fetch all sites in a CSV into flat parquet')
    p_ing.add_argument('--csv', required=True,
        help='Path to CSV file (formula, url)')
    p_ing.add_argument('--days', type=int, default=90,
        help='Days of history per site (default: 90)')
    p_ing.add_argument('--output', '-o', default='externals/ns-parquet-dynisf',
        help='Output directory for Parquet files')
    p_ing.add_argument('--skip-grid', action='store_true',
        help='Skip building the research grid')
    p_ing.add_argument('--quiet', '-q', action='store_true')
    p_ing.add_argument('--dry-run', action='store_true',
        help='Parse CSV and show what would be ingested without fetching')

    # ── split ──
    p_split = sub.add_parser('split',
        help='Chronological train/verification split on flat parquet')
    p_split.add_argument('--input', '-i', required=True,
        help='Flat parquet directory from ingest step')
    p_split.add_argument('--output', '-o', required=True,
        help='Output directory (will contain training/ + verification/)')
    p_split.add_argument('--train-frac', type=float, default=0.8,
        help='Fraction of data for training (default: 0.8)')
    p_split.add_argument('--quiet', '-q', action='store_true')

    # ── merge ──
    p_merge = sub.add_parser('merge',
        help='Merge split staging data into the main terrarium')
    p_merge.add_argument('--staging', '-s', required=True,
        help='Staging directory (with training/ + verification/)')
    p_merge.add_argument('--terrarium', '-t',
        default='externals/ns-parquet',
        help='Main terrarium directory (default: externals/ns-parquet)')
    p_merge.add_argument('--quiet', '-q', action='store_true')

    # ── pipeline (ingest → split → merge) ──
    p_pipe = sub.add_parser('pipeline',
        help='Full pipeline: ingest → split → merge into terrarium')
    p_pipe.add_argument('--csv', required=True,
        help='Path to CSV file (formula, url)')
    p_pipe.add_argument('--days', type=int, default=90,
        help='Days of history per site (default: 90)')
    p_pipe.add_argument('--terrarium', '-t',
        default='externals/ns-parquet',
        help='Main terrarium directory')
    p_pipe.add_argument('--staging', '-s',
        default='externals/ns-parquet-dynisf',
        help='Staging directory for intermediate files')
    p_pipe.add_argument('--train-frac', type=float, default=0.8,
        help='Fraction of data for training (default: 0.8)')
    p_pipe.add_argument('--skip-grid', action='store_true')
    p_pipe.add_argument('--quiet', '-q', action='store_true')
    p_pipe.add_argument('--dry-run', action='store_true')

    args = parser.parse_args()

    if args.command == 'ingest' or args.command is None:
        # Backwards compat: bare invocation = ingest
        if args.command is None:
            # Re-parse with legacy flags
            parser.add_argument('--csv', required=True)
            parser.add_argument('--days', type=int, default=90)
            parser.add_argument('--output', '-o',
                                default='externals/ns-parquet-dynisf')
            parser.add_argument('--skip-grid', action='store_true')
            parser.add_argument('--quiet', '-q', action='store_true')
            parser.add_argument('--dry-run', action='store_true')
            args = parser.parse_args()
        batch_ingest(args.csv, args.days, args.output,
                     quiet=args.quiet, skip_grid=args.skip_grid,
                     dry_run=args.dry_run)

    elif args.command == 'split':
        print(f'Splitting {args.input} → {args.output}/')
        summary = split_chronological(
            args.input, args.output,
            train_frac=args.train_frac, quiet=args.quiet)
        print(f'\n{len(summary)} patients split.')

    elif args.command == 'merge':
        print(f'Merging {args.staging} → {args.terrarium}/')
        merge_into_terrarium(
            args.staging, args.terrarium, quiet=args.quiet)
        print('Merge complete.')

    elif args.command == 'pipeline':
        staging = args.staging
        split_dir = staging + '-split'

        # Step 1: Ingest
        if not args.dry_run:
            batch_ingest(args.csv, args.days, staging,
                         quiet=args.quiet, skip_grid=args.skip_grid)
        else:
            batch_ingest(args.csv, args.days, staging,
                         quiet=args.quiet, dry_run=True)
            return

        # Step 2: Split
        print(f'\n{"═" * 60}')
        print(f'Splitting → {split_dir}/')
        print(f'{"═" * 60}')
        split_chronological(staging, split_dir,
                            train_frac=args.train_frac, quiet=args.quiet)

        # Step 3: Merge into terrarium
        print(f'\n{"═" * 60}')
        print(f'Merging into terrarium → {args.terrarium}/')
        print(f'{"═" * 60}')
        merge_into_terrarium(split_dir, args.terrarium, quiet=args.quiet)
        print('\nPipeline complete.')


if __name__ == '__main__':
    main()
