#!/usr/bin/env python3
"""
Build a tiny terrarium for smoke tests.

Slices the full terrarium down to 2-3 patients × 7 days,
producing identical schema at ~1% the size. Designed for
fast development loops: load in <50ms, run a smoke test,
iterate on experiment code.

Usage:
    python3 -m tools.ns2parquet.tiny_terrarium \
        --input externals/ns-parquet/training \
        --output externals/ns-parquet-tiny/training \
        --patients a,b \
        --days 7

Defaults: patients a (Loop) + b (Trio/oref0), 7 days from midpoint.
"""

import argparse, json, os, sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


DEFAULT_PATIENTS = ['a', 'b']
DEFAULT_DAYS = 7
PARQUET_FILES = [
    'grid.parquet', 'entries.parquet', 'treatments.parquet',
    'devicestatus.parquet', 'profiles.parquet',
]


def find_time_window(grid: pd.DataFrame, days: int):
    """Pick a window from the middle of the dataset for best coverage."""
    times = pd.to_datetime(grid['time'], utc=True)
    midpoint = times.min() + (times.max() - times.min()) / 2
    half = pd.Timedelta(days=days) / 2
    return midpoint - half, midpoint + half


def slice_parquet(input_dir: Path, output_dir: Path,
                  patients: list, days: int, verbose: bool = True):
    """Slice each parquet file to the selected patients and time window."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine time window from grid
    grid = pd.read_parquet(input_dir / 'grid.parquet')
    grid_subset = grid[grid['patient_id'].isin(patients)]
    if len(grid_subset) == 0:
        print(f"ERROR: No data for patients {patients}", file=sys.stderr)
        sys.exit(1)

    t_start, t_end = find_time_window(grid_subset, days)
    if verbose:
        print(f"  Time window: {t_start.date()} → {t_end.date()} ({days} days)")
        print(f"  Patients: {', '.join(patients)}")

    stats = {}
    for fname in PARQUET_FILES:
        src = input_dir / fname
        if not src.exists():
            if verbose:
                print(f"  {fname}: not found, skipping")
            continue

        df = pd.read_parquet(src)

        # Filter by patient
        if 'patient_id' in df.columns:
            df = df[df['patient_id'].isin(patients)]

        # Filter by time window
        time_col = None
        for candidate in ['time', 'created_at', 'date', 'dateString']:
            if candidate in df.columns:
                time_col = candidate
                break

        if time_col and fname != 'profiles.parquet':
            ts = pd.to_datetime(df[time_col], utc=True)
            df = df[(ts >= t_start) & (ts <= t_end)]

        dst = output_dir / fname
        df.to_parquet(dst, index=False)
        stats[fname] = len(df)
        if verbose:
            print(f"  {fname}: {len(df):,} rows")

    return t_start, t_end, stats


def main():
    parser = argparse.ArgumentParser(
        description='Build a tiny terrarium for smoke tests')
    parser.add_argument('--input', '-i', required=True,
                        help='Full terrarium directory (e.g. externals/ns-parquet/training)')
    parser.add_argument('--output', '-o', required=True,
                        help='Output directory for tiny terrarium')
    parser.add_argument('--patients', '-p', default=','.join(DEFAULT_PATIENTS),
                        help=f'Comma-separated patient IDs (default: {",".join(DEFAULT_PATIENTS)})')
    parser.add_argument('--days', '-d', type=int, default=DEFAULT_DAYS,
                        help=f'Number of days to include (default: {DEFAULT_DAYS})')
    args = parser.parse_args()

    patients = [p.strip() for p in args.patients.split(',')]
    input_dir = Path(args.input)
    output_dir = Path(args.output)

    print(f"Building tiny terrarium → {output_dir}/")
    t_start, t_end, stats = slice_parquet(input_dir, output_dir, patients, args.days)

    # Write manifest
    manifest = {
        'type': 'tiny_terrarium',
        'built': datetime.now(timezone.utc).isoformat(),
        'source': str(input_dir),
        'patients': patients,
        'days': args.days,
        'window': [t_start.isoformat(), t_end.isoformat()],
        'rows': stats,
    }
    manifest_path = output_dir.parent / 'manifest.json' if output_dir.name in ('training', 'verification') else output_dir / 'manifest.json'
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2, default=str)

    total_bytes = sum(
        (output_dir / f).stat().st_size for f in PARQUET_FILES
        if (output_dir / f).exists()
    )
    total_rows = sum(stats.values())
    print(f"\n  Tiny terrarium ready: {total_rows:,} rows, "
          f"{total_bytes / 1024:.0f} KB on disk")
    print(f"  Load with: NS_PARQUET={output_dir}")


if __name__ == '__main__':
    main()
