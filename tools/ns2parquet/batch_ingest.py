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
import signal
import sys
import time
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Tuple, Optional

# Per-site timeout (seconds).  Prevents infinite hangs on unresponsive servers.
_SITE_TIMEOUT = 300  # 5 minutes


class _SiteTimeout(Exception):
    """Raised when a single site takes too long."""


def _alarm_handler(signum, frame):
    raise _SiteTimeout('site ingest timed out')


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


def _existing_patients(output: str) -> set:
    """Return set of patient_ids already present in the output grid."""
    grid_path = Path(output) / 'grid.parquet'
    if not grid_path.exists():
        return set()
    try:
        import pyarrow.parquet as pq
        t = pq.read_table(grid_path, columns=['patient_id'])
        return set(t.column('patient_id').to_pylist())
    except Exception:
        return set()


def _auth_failed_patients(output: str) -> set:
    """Return set of patient_ids that failed with auth errors (401/403).

    These should NOT be retried without fresh tokens.  Checks both the
    ``error_kind`` field (new format) and the ``status`` string (old format).
    """
    manifest_path = Path(output) / 'manifest.json'
    if not manifest_path.exists():
        return set()
    try:
        m = json.load(open(manifest_path))
        result = set()
        for p in m.get('patients', []):
            if p.get('error_kind') == 'auth':
                result.add(p['patient_id'])
            elif any(k in p.get('status', '').lower()
                     for k in ('403', '401', 'forbidden', 'unauthorized')):
                result.add(p['patient_id'])
        return result
    except Exception:
        return set()


def batch_ingest(csv_path: str, days: int, output: str,
                 quiet: bool = False, skip_grid: bool = False,
                 dry_run: bool = False, resume: bool = True,
                 retry_network: bool = False,
                 site_timeout: int = _SITE_TIMEOUT,
                 keep_json: str = None) -> dict:
    """Ingest every site in *csv_path* into *output* directory.

    When *resume* is True (default), patients already in the output
    parquet are skipped automatically.

    When *retry_network* is True, only sites that previously failed with
    network errors (timeouts, connection issues) are retried.  Sites that
    failed with auth errors (401/403) are skipped — they need fresh tokens.

    Returns a manifest dict with per-patient metadata.
    """
    from .ns_fetch import parse_ns_url
    from .cli import _generate_opaque_id, cmd_ingest

    rows = parse_csv(csv_path)
    if not rows:
        print(f'ERROR: No valid rows in {csv_path}', file=sys.stderr)
        return {}

    already_done = _existing_patients(output) if resume else set()
    auth_failed = _auth_failed_patients(output) if retry_network else set()

    if not quiet:
        print(f'Batch ingest: {len(rows)} sites, {days} days each')
        if already_done:
            print(f'Resuming: {len(already_done)} patients already ingested')
        if auth_failed:
            print(f'Skipping: {len(auth_failed)} patients with auth errors '
                  f'(need fresh tokens)')
        print(f'Output: {output}/')
        print()

    Path(output).mkdir(parents=True, exist_ok=True)

    manifest_patients = []
    results = {'ok': 0, 'fail': 0, 'skip': 0}

    for idx, (annotation, raw_url) in enumerate(rows, 1):
        base_url, token = parse_ns_url(raw_url)
        opaque_id = _generate_opaque_id(base_url)

        if opaque_id in already_done:
            if not quiet:
                print(f'[{idx}/{len(rows)}] {opaque_id}  SKIP (already ingested)')
            manifest_patients.append({
                'patient_id': opaque_id,
                'annotation': annotation,
                'status': 'already-ingested',
            })
            results['skip'] += 1
            continue

        if retry_network and opaque_id in auth_failed:
            if not quiet:
                print(f'[{idx}/{len(rows)}] {opaque_id}  SKIP (auth error — '
                      f'needs fresh token)')
            manifest_patients.append({
                'patient_id': opaque_id,
                'annotation': annotation,
                'status': 'auth-skip',
                'error_kind': 'auth',
            })
            results['skip'] += 1
            continue

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
            keep_json=keep_json,
        )

        try:
            old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
            signal.alarm(site_timeout)
            try:
                rc = cmd_ingest(ingest_args)
                if rc and rc != 0:
                    raise RuntimeError(f'ingest returned {rc}')
                results['ok'] += 1
                status = 'ok'
                error_kind = None
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        except _SiteTimeout:
            if not quiet:
                print(f'  TIMEOUT: skipping after {site_timeout}s')
            results['fail'] += 1
            status = f'timeout after {site_timeout}s'
            error_kind = 'network'
        except urllib.error.HTTPError as e:
            if not quiet:
                print(f'  HTTP {e.code}: {e.reason}')
            results['fail'] += 1
            status = f'http-{e.code}: {e.reason}'
            error_kind = 'auth' if e.code in (401, 403) else 'network'
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            if not quiet:
                print(f'  NETWORK ERROR: {e}')
            results['fail'] += 1
            status = f'network: {e}'
            error_kind = 'network'
        except Exception as e:
            if not quiet:
                print(f'  ERROR: {e}')
            results['fail'] += 1
            status = f'error: {e}'
            # Classify: if the string contains 403/401/Forbidden, it's auth
            err_str = str(e).lower()
            if '403' in err_str or '401' in err_str or 'forbidden' in err_str:
                error_kind = 'auth'
            else:
                error_kind = 'network'

        manifest_patients.append({
            'patient_id': opaque_id,
            'annotation': annotation,
            'status': status,
            **(dict(error_kind=error_kind) if error_kind else {}),
        })

        # Be polite to remote servers — longer pause after failures
        if status == 'ok':
            time.sleep(3.0)
        else:
            time.sleep(5.0)

    # Write manifest — merge with existing to preserve error classifications
    manifest_path = Path(output) / 'manifest.json'

    # Load existing patient data to preserve info from previous runs
    existing_by_id = {}
    if manifest_path.exists():
        try:
            old = json.load(open(manifest_path))
            for p in old.get('patients', []):
                existing_by_id[p['patient_id']] = p
        except Exception:
            pass

    # Merge: new results take priority, but carry forward old data for
    # patients that were skipped this run
    merged_patients = []
    seen = set()
    for p in manifest_patients:
        pid = p['patient_id']
        seen.add(pid)
        if p.get('status') in ('already-ingested', 'auth-skip'):
            # Preserve the richer entry from a previous run
            merged_patients.append(existing_by_id.get(pid, p))
        else:
            merged_patients.append(p)
    # Carry forward any patients from old manifest not in this CSV
    for pid, old_p in existing_by_id.items():
        if pid not in seen:
            merged_patients.append(old_p)

    manifest = {
        'built': datetime.now(timezone.utc).isoformat(),
        'source': f'batch_ingest({Path(csv_path).name})',
        'days_requested': days,
        'patients': merged_patients,
        'totals': results,
    }

    if not dry_run:
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


def reconvert_from_json(json_dir: str, output: str,
                        skip_grid: bool = False,
                        quiet: bool = False) -> None:
    """Rebuild parquet from previously staged JSON directories.

    Expects ``json_dir`` to contain subdirectories named by patient ID,
    each with entries.json, treatments.json, devicestatus.json, etc.
    This allows offline re-conversion after schema/normalization changes
    without hitting the Nightscout servers again.
    """
    import shutil
    from .cli import cmd_convert

    json_path = Path(json_dir)
    patient_dirs = sorted(
        d for d in json_path.iterdir()
        if d.is_dir() and (d / 'entries.json').exists()
    )
    if not patient_dirs:
        print(f'No patient JSON directories found in {json_dir}',
              file=sys.stderr)
        return

    # Clear old parquet output so we get a clean rebuild
    out_path = Path(output)
    for pq_file in out_path.glob('*.parquet'):
        pq_file.unlink()

    if not quiet:
        print(f'Reconverting {len(patient_dirs)} patients from {json_dir}/')
        print(f'Output: {output}/')
        print()

    ok = 0
    for idx, pdir in enumerate(patient_dirs, 1):
        patient_id = pdir.name
        if not quiet:
            print(f'[{idx}/{len(patient_dirs)}] {patient_id}')
        try:
            conv_args = argparse.Namespace(
                input=str(pdir),
                patient_id=patient_id,
                output=output,
                append=True,
                quiet=quiet,
                skip_grid=skip_grid,
                opaque_ids=False,
            )
            cmd_convert(conv_args)
            ok += 1
        except Exception as e:
            print(f'  ERROR: {e}', file=sys.stderr)

    if not quiet:
        print(f'\nReconverted {ok}/{len(patient_dirs)} patients → {output}/')


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
    p_ing.add_argument('--retry-network', action='store_true',
        help='Retry only network-failed sites; skip auth errors (403)')
    p_ing.add_argument('--site-timeout', type=int, default=_SITE_TIMEOUT,
        help=f'Per-site timeout in seconds (default: {_SITE_TIMEOUT})')
    p_ing.add_argument('--keep-json',
        help='Persist raw JSON to this directory (enables offline reconvert)')

    # ── reconvert ──
    p_reconv = sub.add_parser('reconvert',
        help='Rebuild parquet from previously staged JSON (offline)')
    p_reconv.add_argument('--json-dir', required=True,
        help='Directory containing patient JSON subdirectories')
    p_reconv.add_argument('--output', '-o', default='externals/ns-parquet-dynisf',
        help='Output directory for Parquet files')
    p_reconv.add_argument('--skip-grid', action='store_true')
    p_reconv.add_argument('--quiet', '-q', action='store_true')

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
                     dry_run=args.dry_run,
                     retry_network=getattr(args, 'retry_network', False),
                     site_timeout=getattr(args, 'site_timeout', _SITE_TIMEOUT),
                     keep_json=getattr(args, 'keep_json', None))

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

    elif args.command == 'reconvert':
        reconvert_from_json(args.json_dir, args.output,
                            skip_grid=args.skip_grid, quiet=args.quiet)

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
