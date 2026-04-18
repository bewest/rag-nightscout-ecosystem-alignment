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


def main():
    parser = argparse.ArgumentParser(
        description='Batch-ingest Nightscout sites from a CSV file')
    parser.add_argument('--csv', required=True,
        help='Path to CSV file (formula, url)')
    parser.add_argument('--days', type=int, default=90,
        help='Days of history per site (default: 90)')
    parser.add_argument('--output', '-o', default='externals/ns-parquet-dynisf',
        help='Output directory for Parquet files')
    parser.add_argument('--skip-grid', action='store_true',
        help='Skip building the research grid')
    parser.add_argument('--quiet', '-q', action='store_true')
    parser.add_argument('--dry-run', action='store_true',
        help='Parse CSV and show what would be ingested without fetching')

    args = parser.parse_args()
    batch_ingest(args.csv, args.days, args.output,
                 quiet=args.quiet, skip_grid=args.skip_grid,
                 dry_run=args.dry_run)


if __name__ == '__main__':
    main()
