#!/usr/bin/env python3
"""
benchmark_parquet_vs_json.py — Repeatable performance benchmark
================================================================

Measures wall-clock time for data loading operations via:
  1. JSON path  (build_nightscout_grid → build_continuous_pk_features)
  2. Parquet path (load_parquet_grid → load_parquet_patients)

Runs multiple trials per operation, reports median/mean/min with
confidence intervals. Outputs machine-readable JSON + human table.

Usage:
    python3 benchmark_parquet_vs_json.py [--trials 3] [--patients a,b,c]
"""

import sys, os, time, json, gc, argparse, platform, subprocess
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO / 'tools' / 'cgmencode'))
sys.path.insert(0, str(_REPO / 'tools'))

import numpy as np
import pandas as pd

# Paths
NS_DATA = _REPO / 'externals' / 'ns-data' / 'patients'
NS_PARQUET = _REPO / 'externals' / 'ns-parquet' / 'training'

# Import data loaders
from cgmencode.real_data_adapter import (
    build_nightscout_grid, load_parquet_grid, load_parquet_patients
)
from cgmencode.continuous_pk import build_continuous_pk_features
from cgmencode.exp_metabolic_flux import load_patients as json_load_patients


def get_system_info():
    """Collect system metadata for reproducibility."""
    info = {
        'platform': platform.platform(),
        'python': platform.python_version(),
        'cpu': platform.processor() or 'unknown',
        'cpu_count': os.cpu_count(),
    }
    try:
        mem = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
        info['ram_gb'] = round(mem / (1024**3), 1)
    except (ValueError, OSError):
        info['ram_gb'] = 'unknown'
    return info


def get_data_sizes():
    """Measure on-disk sizes."""
    sizes = {'json': {}, 'parquet': {}}
    json_total = 0
    if NS_DATA.exists():
        for pdir in sorted(NS_DATA.iterdir()):
            tdir = pdir / 'training'
            if tdir.is_dir():
                sz = sum(f.stat().st_size for f in tdir.rglob('*') if f.is_file())
                sizes['json'][pdir.name] = sz
                json_total += sz
    sizes['json']['_total'] = json_total

    pq_total = 0
    if NS_PARQUET.exists():
        for f in NS_PARQUET.glob('*.parquet'):
            sz = f.stat().st_size
            sizes['parquet'][f.name] = sz
            pq_total += sz
    sizes['parquet']['_total'] = pq_total

    return sizes


def timed(fn, *args, **kwargs):
    """Run fn, return (result, elapsed_seconds)."""
    gc.collect()
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    elapsed = time.perf_counter() - t0
    return result, elapsed


def bench_json_single(patient_id, trials=3):
    """Benchmark: JSON load → grid for one patient."""
    data_path = str(NS_DATA / patient_id / 'training')
    if not os.path.isdir(data_path):
        return None
    times = []
    rows = 0
    for _ in range(trials):
        result, elapsed = timed(build_nightscout_grid, data_path, verbose=False)
        times.append(elapsed)
        if result:
            rows = len(result[0])
    return {'times': times, 'rows': rows}


def bench_parquet_single(patient_id, trials=3):
    """Benchmark: Parquet load → grid for one patient."""
    if not NS_PARQUET.exists():
        return None
    times = []
    rows = 0
    for _ in range(trials):
        result, elapsed = timed(load_parquet_grid, str(NS_PARQUET),
                                patient_filter=patient_id, verbose=False)
        times.append(elapsed)
        if result and patient_id in result:
            rows = len(result[patient_id][0])
    return {'times': times, 'rows': rows}


def bench_json_all(patient_ids, trials=1):
    """Benchmark: JSON load all patients + PK features."""
    times = []
    count = 0
    for _ in range(trials):
        result, elapsed = timed(
            json_load_patients, str(NS_DATA),
            patient_filter=None, verbose=False)
        times.append(elapsed)
        count = len(result)
    return {'times': times, 'patients': count}


def bench_parquet_all(patient_ids, trials=3):
    """Benchmark: Parquet load all patients + PK features."""
    times = []
    count = 0
    for _ in range(trials):
        result, elapsed = timed(
            load_parquet_patients, str(NS_PARQUET), verbose=False)
        times.append(elapsed)
        count = len(result)
    return {'times': times, 'patients': count}


def bench_parquet_grid_only(trials=3):
    """Benchmark: Parquet grid read only (no PK build)."""
    times = []
    rows = 0
    for _ in range(trials):
        gc.collect()
        t0 = time.perf_counter()
        grid = pd.read_parquet(str(NS_PARQUET / 'grid.parquet'))
        elapsed = time.perf_counter() - t0
        times.append(elapsed)
        rows = len(grid)
    return {'times': times, 'rows': rows}


def bench_parquet_filtered_read(patient_id, columns=None, trials=5):
    """Benchmark: Parquet filtered read (column subset + row filter)."""
    times = []
    rows = 0
    for _ in range(trials):
        gc.collect()
        t0 = time.perf_counter()
        grid = pd.read_parquet(
            str(NS_PARQUET / 'grid.parquet'),
            columns=columns,
            filters=[('patient_id', '==', patient_id)]
        )
        elapsed = time.perf_counter() - t0
        times.append(elapsed)
        rows = len(grid)
    return {'times': times, 'rows': rows}


def stats_summary(times):
    """Compute summary statistics for a list of times."""
    arr = np.array(times)
    return {
        'n': len(arr),
        'mean': round(float(arr.mean()), 4),
        'median': round(float(np.median(arr)), 4),
        'min': round(float(arr.min()), 4),
        'max': round(float(arr.max()), 4),
        'std': round(float(arr.std()), 4),
    }


def format_time(seconds):
    """Human-friendly time formatting."""
    if seconds < 0.001:
        return f"{seconds*1_000_000:.0f}µs"
    elif seconds < 1:
        return f"{seconds*1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    else:
        return f"{seconds/60:.1f}min"


def format_size(nbytes):
    """Human-friendly size formatting."""
    if nbytes < 1024:
        return f"{nbytes}B"
    elif nbytes < 1024**2:
        return f"{nbytes/1024:.1f}KB"
    elif nbytes < 1024**3:
        return f"{nbytes/1024**2:.1f}MB"
    else:
        return f"{nbytes/1024**3:.2f}GB"


def main():
    parser = argparse.ArgumentParser(description='Benchmark JSON vs Parquet data loading')
    parser.add_argument('--trials', type=int, default=3, help='Trials per benchmark')
    parser.add_argument('--patients', type=str, default=None,
                        help='Comma-separated patient IDs for single-patient benchmarks')
    parser.add_argument('--skip-json-all', action='store_true',
                        help='Skip the slow full JSON benchmark')
    args = parser.parse_args()

    patients = args.patients.split(',') if args.patients else ['a', 'b', 'c']
    trials = args.trials

    print("=" * 70)
    print("  Parquet vs JSON Performance Benchmark")
    print("=" * 70)

    # System info
    sysinfo = get_system_info()
    print(f"\n  System: {sysinfo['platform']}")
    print(f"  Python: {sysinfo['python']}")
    print(f"  CPUs: {sysinfo['cpu_count']}, RAM: {sysinfo['ram_gb']}GB")
    print(f"  Trials: {trials}")

    # Data sizes
    sizes = get_data_sizes()
    json_total = sizes['json'].get('_total', 0)
    pq_total = sizes['parquet'].get('_total', 0)
    compression = json_total / pq_total if pq_total > 0 else 0
    print(f"\n  Data sizes:")
    print(f"    JSON (11 patients): {format_size(json_total)}")
    print(f"    Parquet (terrarium): {format_size(pq_total)}")
    print(f"    Compression ratio: {compression:.1f}×")

    results = {
        'system': sysinfo,
        'data_sizes': {
            'json_bytes': json_total,
            'parquet_bytes': pq_total,
            'compression_ratio': round(compression, 1),
        },
        'benchmarks': {},
    }

    # ── Benchmark 1: Single patient grid load ──
    print(f"\n{'─'*70}")
    print(f"  Benchmark 1: Single Patient Grid Load ({trials} trials each)")
    print(f"{'─'*70}")
    print(f"  {'Patient':<10} {'JSON':<15} {'Parquet':<15} {'Speedup'}")
    print(f"  {'─'*55}")

    for pid in patients:
        json_r = bench_json_single(pid, trials=trials)
        pq_r = bench_parquet_single(pid, trials=trials)

        if json_r and pq_r:
            js = stats_summary(json_r['times'])
            ps = stats_summary(pq_r['times'])
            speedup = js['median'] / ps['median'] if ps['median'] > 0 else float('inf')
            print(f"  {pid:<10} {format_time(js['median']):<15} "
                  f"{format_time(ps['median']):<15} {speedup:.0f}×")
            results['benchmarks'][f'single_{pid}'] = {
                'json': js, 'parquet': ps,
                'speedup': round(speedup, 1),
                'rows': json_r['rows'],
            }

    # ── Benchmark 2: Parquet raw grid read (all patients) ──
    print(f"\n{'─'*70}")
    print(f"  Benchmark 2: Parquet Raw Grid Read — All Patients ({trials} trials)")
    print(f"{'─'*70}")

    pq_grid = bench_parquet_grid_only(trials=trials)
    gs = stats_summary(pq_grid['times'])
    print(f"  grid.parquet → DataFrame: {format_time(gs['median'])} "
          f"({pq_grid['rows']:,} rows)")
    results['benchmarks']['parquet_grid_raw'] = {
        'stats': gs, 'rows': pq_grid['rows']}

    # ── Benchmark 3: Parquet filtered read ──
    print(f"\n{'─'*70}")
    print(f"  Benchmark 3: Parquet Filtered Read — Single Patient ({trials+2} trials)")
    print(f"{'─'*70}")

    for pid in patients[:2]:
        # Full columns
        full = bench_parquet_filtered_read(pid, trials=trials+2)
        fs = stats_summary(full['times'])

        # Minimal columns (glucose + iob only)
        minimal = bench_parquet_filtered_read(
            pid, columns=['patient_id', 'glucose', 'iob', 'time'],
            trials=trials+2)
        ms = stats_summary(minimal['times'])

        print(f"  {pid} (all cols): {format_time(fs['median'])} ({full['rows']:,} rows)")
        print(f"  {pid} (4 cols):   {format_time(ms['median'])} ({minimal['rows']:,} rows)")
        results['benchmarks'][f'filtered_{pid}'] = {
            'all_cols': fs, 'minimal_cols': ms, 'rows': full['rows']}

    # ── Benchmark 4: Full pipeline (all patients + PK) ──
    print(f"\n{'─'*70}")
    print(f"  Benchmark 4: Full Pipeline — All Patients + PK Features")
    print(f"{'─'*70}")

    # Parquet (multiple trials — it's fast)
    pq_all = bench_parquet_all(patients, trials=trials)
    pas = stats_summary(pq_all['times'])
    print(f"  Parquet pipeline: {format_time(pas['median'])} "
          f"({pq_all['patients']} patients, {trials} trials)")

    # JSON (1 trial — it's slow)
    if not args.skip_json_all:
        print(f"  JSON pipeline: running (1 trial, this takes a few minutes)...")
        json_all = bench_json_all(patients, trials=1)
        jas = stats_summary(json_all['times'])
        speedup_all = jas['median'] / pas['median'] if pas['median'] > 0 else 0
        print(f"  JSON pipeline:    {format_time(jas['median'])} "
              f"({json_all['patients']} patients, 1 trial)")
        print(f"  Speedup:          {speedup_all:.1f}×")
        results['benchmarks']['full_pipeline'] = {
            'json': jas, 'parquet': pas,
            'speedup': round(speedup_all, 1),
            'patients': pq_all['patients'],
        }
    else:
        print(f"  JSON pipeline: skipped (--skip-json-all)")
        results['benchmarks']['full_pipeline'] = {
            'parquet': pas, 'patients': pq_all['patients']}

    # ── Benchmark 5: Incremental access patterns ──
    print(f"\n{'─'*70}")
    print(f"  Benchmark 5: Incremental Access — Add 1 Patient")
    print(f"{'─'*70}")

    # Load 1 patient, then 2, then 3 via parquet
    for n in [1, 3, 6, 11]:
        gc.collect()
        t0 = time.perf_counter()
        result = load_parquet_patients(str(NS_PARQUET),
                                       max_patients=n, verbose=False)
        elapsed = time.perf_counter() - t0
        print(f"  {n:>2} patients: {format_time(elapsed)} "
              f"({sum(len(p['df']) for p in result):,} total rows)")
        results['benchmarks'][f'incremental_{n}'] = {
            'time': round(elapsed, 4), 'patients': len(result)}

    # ── Summary table ──
    print(f"\n{'='*70}")
    print(f"  Summary")
    print(f"{'='*70}")
    print(f"\n  {'Operation':<40} {'JSON':<12} {'Parquet':<12} {'Speedup'}")
    print(f"  {'─'*70}")

    for pid in patients:
        bk = f'single_{pid}'
        if bk in results['benchmarks']:
            b = results['benchmarks'][bk]
            print(f"  Load patient {pid} (grid only){'':<14} "
                  f"{format_time(b['json']['median']):<12} "
                  f"{format_time(b['parquet']['median']):<12} "
                  f"{b['speedup']:.0f}×")

    if 'full_pipeline' in results['benchmarks']:
        fp = results['benchmarks']['full_pipeline']
        if 'json' in fp:
            print(f"  Full pipeline (11 patients + PK){'':<8} "
                  f"{format_time(fp['json']['median']):<12} "
                  f"{format_time(fp['parquet']['median']):<12} "
                  f"{fp['speedup']:.0f}×")

    print(f"\n  On-disk: {format_size(json_total)} → "
          f"{format_size(pq_total)} ({compression:.0f}× compression)")

    # Save
    outpath = str(_REPO / 'externals' / 'experiments' / 'benchmark-parquet-vs-json.json')
    with open(outpath, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Results → {outpath}")


if __name__ == '__main__':
    main()
