#!/usr/bin/env python3
"""
validate_parquet.py — Validate ns2parquet output against original JSON pipeline.

Three-level validation:
  1. COLUMN MATCH — Compare core grid columns (glucose, iob, cob, bolus, carbs, net_basal)
     loaded from JSON via build_nightscout_grid() vs loaded from parquet
  2. CLINICAL METRICS — Replicate glucose_metrics() (TIR, TBR, TAR, mean, CV)
     from both sources and compare
  3. TREATMENT COUNTS — Compare bolus/carb event counts

Usage:
    python3 tools/ns2parquet/validate_parquet.py --parquet-dir /path/to/parquet
    python3 tools/ns2parquet/validate_parquet.py  # uses PARQUET_DIR env var or default
"""

import argparse
import os
import sys
import time
import numpy as np
import pandas as pd
from pathlib import Path

PATIENTS_DIR = Path(__file__).resolve().parent.parent.parent / 'externals' / 'ns-data' / 'patients'
DEFAULT_PARQUET_DIR = os.environ.get(
    'NS2PARQUET_VALIDATE_DIR',
    str(Path(__file__).resolve().parent.parent.parent / 'output' / 'validate'),
)

TARGET_LOW = 70
TARGET_HIGH = 180


def glucose_metrics(glucose):
    """Standard clinical metrics — identical to exp_pharmacokinetics_2021.py:49."""
    valid = glucose[np.isfinite(glucose)]
    if len(valid) < 100:
        return {'tir': np.nan, 'tbr': np.nan, 'tar': np.nan, 'mean': np.nan, 'cv': np.nan}
    return {
        'tir': float(np.mean((valid >= TARGET_LOW) & (valid <= TARGET_HIGH)) * 100),
        'tbr': float(np.mean(valid < TARGET_LOW) * 100),
        'tar': float(np.mean(valid > TARGET_HIGH) * 100),
        'mean': float(np.nanmean(valid)),
        'cv': float(np.nanstd(valid) / np.nanmean(valid) * 100) if np.nanmean(valid) > 0 else np.nan,
    }


def load_json_grid(patient_dir):
    """Load via the original JSON pipeline (build_nightscout_grid).

    Tries to import from cgmencode; returns None if unavailable.
    """
    try:
        from cgmencode.real_data_adapter import build_nightscout_grid
    except ImportError:
        print('  WARNING: cgmencode not available — skipping JSON comparison',
              file=sys.stderr)
        return None, None
    df, features_8ch = build_nightscout_grid(str(patient_dir), verbose=False)
    return df, features_8ch


def load_parquet_grid(parquet_dir, patient_id):
    """Load from parquet grid."""
    return pd.read_parquet(
        parquet_dir / 'grid.parquet',
        filters=[('patient_id', '=', patient_id)],
    )


def compare_column(json_vals, parquet_vals, col_name, atol=0.5):
    """Compare two arrays, return (match_pct, max_diff, mean_diff)."""
    # Align by dropping NaN from both
    mask = np.isfinite(json_vals) & np.isfinite(parquet_vals)
    if mask.sum() == 0:
        return 0.0, np.nan, np.nan
    j = json_vals[mask]
    p = parquet_vals[mask]
    diffs = np.abs(j - p)
    match_pct = float(np.mean(diffs < atol) * 100)
    return match_pct, float(np.max(diffs)), float(np.mean(diffs))


def validate_patient(patient_id, parquet_dir, verbose=True):
    """Run all validation checks for one patient."""
    patient_dir = PATIENTS_DIR / patient_id / 'training'
    if not (patient_dir / 'entries.json').exists():
        return None

    results = {'patient': patient_id}

    # ── Load from both sources ──────────────────────────────────────
    t0 = time.time()
    json_df, json_features = load_json_grid(patient_dir)
    json_time = time.time() - t0

    if json_df is None:
        results['status'] = 'SKIP_NO_CGMENCODE'
        return results

    t0 = time.time()
    pq_df = load_parquet_grid(parquet_dir, patient_id)
    parquet_time = time.time() - t0

    results['json_rows'] = len(json_df)
    results['parquet_rows'] = len(pq_df)
    results['json_load_ms'] = round(json_time * 1000)
    results['parquet_load_ms'] = round(parquet_time * 1000)
    results['speedup'] = round(json_time / max(parquet_time, 0.001), 1)

    # ── 1. COLUMN MATCH ─────────────────────────────────────────────
    # Align by timestamp: round both to 5-min grid
    json_df = json_df.copy()
    json_df.index = json_df.index.round('5min')
    json_df = json_df[~json_df.index.duplicated(keep='first')]

    pq_df = pq_df.copy()
    pq_df['time'] = pd.to_datetime(pq_df['time'], utc=True).dt.round('5min')
    pq_df = pq_df.drop_duplicates(subset='time', keep='first')
    pq_df = pq_df.set_index('time')

    # Find overlapping timestamps
    common_idx = json_df.index.intersection(pq_df.index)
    results['common_rows'] = len(common_idx)

    if len(common_idx) == 0:
        results['status'] = 'NO_OVERLAP'
        return results

    json_aligned = json_df.loc[common_idx]
    pq_aligned = pq_df.loc[common_idx]

    col_results = {}
    for col, pq_col, atol in [
        ('glucose', 'glucose', 0.5),
        ('iob', 'iob', 0.05),
        ('cob', 'cob', 0.5),
        ('bolus', 'bolus', 0.01),
        ('carbs', 'carbs', 0.1),
        ('net_basal', 'net_basal', 0.05),
    ]:
        if col not in json_aligned.columns or pq_col not in pq_aligned.columns:
            col_results[col] = {'match_pct': np.nan, 'status': 'MISSING'}
            continue

        j_vals = json_aligned[col].values.astype(float)
        p_vals = pq_aligned[pq_col].values.astype(float)
        match_pct, max_diff, mean_diff = compare_column(j_vals, p_vals, col, atol)

        # Detect "IMPROVED" case: parquet has more non-zero data than JSON
        # (e.g., oref0 IOB extracted by parquet but not by JSON pipeline)
        status = 'PASS' if match_pct >= 99.0 else 'WARN' if match_pct >= 95.0 else 'FAIL'
        if status == 'FAIL' and col in ('iob', 'cob'):
            j_nonzero = np.sum(np.abs(j_vals[np.isfinite(j_vals)]) > 0.01)
            p_nonzero = np.sum(np.abs(p_vals[np.isfinite(p_vals)]) > 0.01)
            # Where JSON has non-zero values, do they match parquet?
            j_has_data = np.isfinite(j_vals) & (np.abs(j_vals) > 0.01)
            p_at_j = p_vals[j_has_data]
            j_at_j = j_vals[j_has_data]
            if len(j_at_j) > 0:
                overlap_match = float(np.mean(np.abs(j_at_j - p_at_j) < atol) * 100)
            else:
                overlap_match = 100.0
            if p_nonzero > j_nonzero and overlap_match >= 99.0:
                status = 'IMPROVED'

        col_results[col] = {
            'match_pct': round(match_pct, 1),
            'max_diff': round(max_diff, 3) if np.isfinite(max_diff) else None,
            'mean_diff': round(mean_diff, 4) if np.isfinite(mean_diff) else None,
            'status': status,
        }

    results['columns'] = col_results

    # ── 2. CLINICAL METRICS ──────────────────────────────────────────
    json_metrics = glucose_metrics(json_aligned['glucose'].values)
    pq_metrics = glucose_metrics(pq_aligned['glucose'].values)

    metric_diffs = {}
    for key in ['tir', 'tbr', 'tar', 'mean', 'cv']:
        j_val = json_metrics[key]
        p_val = pq_metrics[key]
        if np.isfinite(j_val) and np.isfinite(p_val):
            diff = abs(j_val - p_val)
            metric_diffs[key] = {
                'json': round(j_val, 2),
                'parquet': round(p_val, 2),
                'diff': round(diff, 4),
                'status': 'PASS' if diff < 0.1 else 'WARN' if diff < 1.0 else 'FAIL',
            }

    results['clinical_metrics'] = metric_diffs

    # ── 3. TREATMENT COUNTS ──────────────────────────────────────────
    json_bolus_count = int((json_aligned['bolus'] > 0).sum())
    pq_bolus_count = int((pq_aligned['bolus'] > 0).sum())
    json_carb_count = int((json_aligned['carbs'] > 0).sum())
    pq_carb_count = int((pq_aligned['carbs'] > 0).sum())

    results['treatment_counts'] = {
        'bolus': {
            'json': json_bolus_count,
            'parquet': pq_bolus_count,
            'match': json_bolus_count == pq_bolus_count,
        },
        'carbs': {
            'json': json_carb_count,
            'parquet': pq_carb_count,
            'match': json_carb_count == pq_carb_count,
        },
    }

    # ── Overall status ───────────────────────────────────────────────
    all_col_pass = all(v['status'] in ('PASS', 'WARN', 'IMPROVED') for v in col_results.values()
                       if isinstance(v, dict) and 'status' in v)
    all_metric_pass = all(v['status'] in ('PASS', 'WARN') for v in metric_diffs.values())
    has_improvements = any(v.get('status') == 'IMPROVED' for v in col_results.values()
                          if isinstance(v, dict))
    results['status'] = ('IMPROVED' if has_improvements else 'PASS') if (all_col_pass and all_metric_pass) else 'FAIL'

    return results


def print_results(all_results):
    """Print formatted validation report."""
    print()
    print('=' * 80)
    print('  ns2parquet VALIDATION REPORT')
    print('  JSON pipeline (build_nightscout_grid) vs Parquet pipeline')
    print('=' * 80)

    # ── Summary table ────────────────────────────────────────────────
    print()
    print(f'{"Pat":>3} {"Status":>6} {"Rows":>10} '
          f'{"Gluc%":>6} {"IOB%":>5} {"Bolus%":>6} '
          f'{"TIR Δ":>6} {"Mean Δ":>7} '
          f'{"JSON ms":>7} {"PQ ms":>5} {"Speed":>5}')
    print('-' * 80)

    pass_count = 0
    for r in all_results:
        if r is None:
            continue
        pid = r['patient']
        status = r.get('status', '?')
        if status in ('PASS', 'IMPROVED'):
            pass_count += 1

        cols = r.get('columns', {})
        metrics = r.get('clinical_metrics', {})

        gluc_pct = cols.get('glucose', {}).get('match_pct', '?')
        iob_pct = cols.get('iob', {}).get('match_pct', '?')
        bolus_pct = cols.get('bolus', {}).get('match_pct', '?')
        tir_diff = metrics.get('tir', {}).get('diff', '?')
        mean_diff = metrics.get('mean', {}).get('diff', '?')

        print(f'{pid:>3} {status:>6} {r.get("common_rows", 0):>10,} '
              f'{gluc_pct:>6} {iob_pct:>5} {bolus_pct:>6} '
              f'{tir_diff:>6} {mean_diff:>7} '
              f'{r.get("json_load_ms", 0):>7} {r.get("parquet_load_ms", 0):>5} '
              f'{r.get("speedup", 0):>5}x')

    print('-' * 80)
    total = len([r for r in all_results if r])
    print(f'  {pass_count}/{total} patients PASS')
    print()

    # ── Detailed per-patient clinical metrics ────────────────────────
    print('CLINICAL METRICS COMPARISON (JSON → Parquet):')
    print(f'{"Pat":>3} {"TIR(J)":>7} {"TIR(P)":>7} {"TBR(J)":>7} {"TBR(P)":>7} '
          f'{"Mean(J)":>8} {"Mean(P)":>8} {"CV(J)":>6} {"CV(P)":>6}')
    print('-' * 80)

    for r in all_results:
        if r is None:
            continue
        m = r.get('clinical_metrics', {})
        pid = r['patient']
        print(f'{pid:>3} '
              f'{m.get("tir", {}).get("json", "?"):>7} {m.get("tir", {}).get("parquet", "?"):>7} '
              f'{m.get("tbr", {}).get("json", "?"):>7} {m.get("tbr", {}).get("parquet", "?"):>7} '
              f'{m.get("mean", {}).get("json", "?"):>8} {m.get("mean", {}).get("parquet", "?"):>8} '
              f'{m.get("cv", {}).get("json", "?"):>6} {m.get("cv", {}).get("parquet", "?"):>6}')

    print()

    # ── Treatment count comparison ───────────────────────────────────
    print('TREATMENT COUNTS (bolus/carb events at 5-min grid resolution):')
    print(f'{"Pat":>3} {"Bolus(J)":>9} {"Bolus(P)":>9} {"Match":>6} '
          f'{"Carbs(J)":>9} {"Carbs(P)":>9} {"Match":>6}')
    print('-' * 60)

    for r in all_results:
        if r is None:
            continue
        tc = r.get('treatment_counts', {})
        b = tc.get('bolus', {})
        c = tc.get('carbs', {})
        pid = r['patient']
        print(f'{pid:>3} {b.get("json", "?"):>9} {b.get("parquet", "?"):>9} '
              f'{"✓" if b.get("match") else "✗":>6} '
              f'{c.get("json", "?"):>9} {c.get("parquet", "?"):>9} '
              f'{"✓" if c.get("match") else "✗":>6}')

    print()
    print('=' * 80)


def main():
    parser = argparse.ArgumentParser(
        description='Validate ns2parquet output against original JSON pipeline')
    parser.add_argument('--parquet-dir', '-p',
                        default=DEFAULT_PARQUET_DIR,
                        help=f'Directory containing parquet output (default: $NS2PARQUET_VALIDATE_DIR or {DEFAULT_PARQUET_DIR})')
    parser.add_argument('--patients-dir',
                        default=str(PATIENTS_DIR),
                        help='Directory containing patient subdirectories')
    args = parser.parse_args()

    parquet_dir = Path(args.parquet_dir)
    patients_dir = Path(args.patients_dir)

    if not parquet_dir.exists():
        print(f'ERROR: Parquet output not found at {parquet_dir}')
        print(f'Run: python3 -m tools.ns2parquet convert-all '
              f'--patients-dir {patients_dir} --subset training '
              f'--output {parquet_dir}')
        return 1

    patient_ids = sorted([
        d.name for d in patients_dir.iterdir()
        if d.is_dir() and not d.name.startswith('.')
    ])

    print(f'Validating {len(patient_ids)} patients: {", ".join(patient_ids)}')
    print(f'JSON source: {patients_dir}')
    print(f'Parquet source: {parquet_dir}')

    all_results = []
    for pid in patient_ids:
        print(f'  Validating {pid}...', end='', flush=True)
        try:
            r = validate_patient(pid, parquet_dir)
            status = r.get('status', '?') if r else 'SKIP'
            print(f' {status}')
            all_results.append(r)
        except Exception as e:
            print(f' ERROR: {e}')
            all_results.append({'patient': pid, 'status': 'ERROR', 'error': str(e)})

    print_results(all_results)
    return 0


if __name__ == '__main__':
    sys.exit(main())
