#!/usr/bin/env python3
"""Re-score existing forecast experiments with clinical metrics.

Loads saved predictions from forecast experiment runners, applies the full
clinical metrics suite (MARD, Clarke zones, ISO 15197, bias, trend accuracy),
and saves enhanced result JSONs alongside the originals.

Usage:
    # Re-score a specific experiment
    python tools/cgmencode/rescore_forecasts.py --experiment exp366_dilated_tcn

    # Re-score all forecast experiments
    python tools/cgmencode/rescore_forecasts.py --all

    # Just show what would be re-scored (dry run)
    python tools/cgmencode/rescore_forecasts.py --all --dry-run

Note: This requires re-running the models to get raw predictions since
the original result JSONs only store aggregated MAE. For experiments where
models aren't saved, we compute what we can from the stored per-horizon MAE
values (approximate MARD from MAE + population glucose distribution).
"""

import numpy as np
import json, os, sys, argparse, glob
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cgmencode.metrics import (
    compute_mard, compute_clarke_zones, compute_iso15197,
    compute_clinical_forecast_metrics, clarke_zone,
)

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / 'externals' / 'experiments'

# Population glucose distribution for approximate MARD from MAE
# Based on 11-patient pooled data: mean ~155 mg/dL, std ~55 mg/dL
POPULATION_GLUCOSE_MEAN = 155.0
POPULATION_GLUCOSE_STD = 55.0


def approximate_mard_from_mae(mae_mgdl: float,
                              glucose_mean: float = POPULATION_GLUCOSE_MEAN) -> float:
    """Approximate MARD from MAE using population mean glucose.

    This is a rough approximation. True MARD requires per-sample computation.
    MARD ≈ MAE / mean(glucose) is a lower bound since E[|x|/y] ≥ E[|x|]/E[y]
    by Jensen's inequality (1/y is convex).
    """
    if glucose_mean <= 0:
        return float('nan')
    return mae_mgdl / glucose_mean


def approximate_clarke_from_mae(mae_mgdl: float) -> dict:
    """Approximate Clarke zone distribution from MAE using Gaussian error model.

    Assumes errors are normally distributed with std ≈ 1.25 × MAE.
    Simulates 10K samples from population glucose distribution.
    """
    np.random.seed(42)
    n_sim = 10000
    glucose = np.random.normal(POPULATION_GLUCOSE_MEAN, POPULATION_GLUCOSE_STD, n_sim)
    glucose = np.clip(glucose, 40, 400)
    error_std = mae_mgdl * 1.25  # approximate: MAE ≈ 0.8 × std for Gaussian
    errors = np.random.normal(0, error_std, n_sim)
    predictions = glucose + errors
    predictions = np.clip(predictions, 0, 600)

    return compute_clarke_zones(glucose, predictions)


def rescore_from_aggregates(result: dict) -> dict:
    """Compute approximate clinical metrics from stored aggregate MAE values.

    Used when raw predictions aren't available (most existing experiments).
    """
    clinical = {'note': 'approximate_from_aggregates'}

    # Overall MAE
    mae_overall = None
    for key in ['mae_overall_mean', 'mae_overall', 'mae_mgdl']:
        if key in result:
            mae_overall = result[key]
            break

    # Check in summary/variants structure
    if mae_overall is None:
        for k, v in result.items():
            if isinstance(v, dict):
                for kk, vv in v.items():
                    if isinstance(vv, dict) and 'mae_overall_mean' in vv:
                        mae_overall = vv['mae_overall_mean']
                        break

    if mae_overall is None:
        return {'error': 'no MAE found in result'}

    clinical['mae_mgdl'] = mae_overall
    clinical['mard_approx'] = approximate_mard_from_mae(mae_overall)
    clinical['mard_approx_pct'] = clinical['mard_approx'] * 100
    clinical['clarke_approx'] = approximate_clarke_from_mae(mae_overall)
    clinical['iso15197_note'] = 'requires per-sample predictions for accurate assessment'

    # Per-horizon MARD approximation
    per_horizon = {}
    horizon_sources = result.get('mae_per_horizon', {})
    if not horizon_sources:
        # Try to extract from nested structure
        for k, v in result.items():
            if isinstance(v, dict) and 'mae_per_horizon' in v:
                horizon_sources = v['mae_per_horizon']
                break
            if isinstance(v, dict):
                for kk, vv in v.items():
                    if isinstance(vv, dict) and 'mae_per_horizon' in vv:
                        horizon_sources = vv['mae_per_horizon']
                        break
                if horizon_sources:
                    break

    for horizon, mae_h in horizon_sources.items():
        if isinstance(mae_h, (int, float)):
            per_horizon[horizon] = {
                'mae_mgdl': mae_h,
                'mard_approx_pct': approximate_mard_from_mae(mae_h) * 100,
                'clarke_approx': approximate_clarke_from_mae(mae_h),
            }
    if per_horizon:
        clinical['per_horizon'] = per_horizon

    return clinical


def rescore_experiment(filepath: str, dry_run: bool = False) -> dict:
    """Re-score a single experiment result file."""
    with open(filepath) as f:
        result = json.load(f)

    exp_name = Path(filepath).stem
    title = result.get('title', result.get('experiment', exp_name))
    print(f"\n{'='*60}")
    print(f"  {exp_name}: {title}")
    print(f"{'='*60}")

    if dry_run:
        # Just check what MAE values exist
        mae_keys = [k for k in result if 'mae' in k.lower()]
        print(f"  MAE keys found: {mae_keys}")
        return {}

    # Try variants structure (v3/v4 format)
    if 'variants' in result:
        enhanced = {}
        for variant_name, variant_data in result['variants'].items():
            if isinstance(variant_data, dict):
                variant_mae = variant_data.get('mae_overall_mean',
                                variant_data.get('mae_overall'))
                if variant_mae is not None:
                    clinical = rescore_from_aggregates(variant_data)
                    enhanced[variant_name] = clinical
                    mard = clinical.get('mard_approx_pct', '?')
                    ab = clinical.get('clarke_approx', {}).get('zone_AB_pct', '?')
                    if isinstance(ab, float):
                        ab = f"{ab*100:.1f}%"
                    print(f"  {variant_name}: MAE={variant_mae:.1f} → MARD≈{mard:.1f}% Clarke A+B≈{ab}")
        return enhanced

    # Try summary structure
    if 'summary' in result:
        enhanced = {}
        for variant_name, variant_data in result['summary'].items():
            if isinstance(variant_data, dict):
                variant_mae = variant_data.get('mae_overall_mean')
                if variant_mae is not None:
                    clinical = rescore_from_aggregates(variant_data)
                    enhanced[variant_name] = clinical
                    mard = clinical.get('mard_approx_pct', '?')
                    print(f"  {variant_name}: MAE={variant_mae:.1f} → MARD≈{mard:.1f}%")
        return enhanced

    # Direct format
    clinical = rescore_from_aggregates(result)
    mard = clinical.get('mard_approx_pct', '?')
    print(f"  Overall: MARD≈{mard}%")
    return clinical


def find_forecast_experiments():
    """Find all forecast experiment result JSONs."""
    patterns = [
        'exp35[2-9]_*.json', 'exp36[0-8]_*.json',
        'exp*forecast*.json', 'exp*pk*.json',
    ]
    found = set()
    for pattern in patterns:
        for path in RESULTS_DIR.glob(pattern):
            found.add(str(path))
    return sorted(found)


def main():
    parser = argparse.ArgumentParser(
        description='Re-score forecast experiments with clinical metrics')
    parser.add_argument('--experiment', type=str,
                        help='Specific experiment file stem (e.g., exp366_dilated_tcn)')
    parser.add_argument('--all', action='store_true',
                        help='Re-score all forecast experiments')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be re-scored without computing')
    args = parser.parse_args()

    if args.experiment:
        files = [str(RESULTS_DIR / f'{args.experiment}.json')]
    elif args.all:
        files = find_forecast_experiments()
    else:
        parser.print_help()
        return

    print(f"Found {len(files)} forecast experiments to re-score")

    all_enhanced = {}
    for filepath in files:
        if not os.path.exists(filepath):
            print(f"  Not found: {filepath}")
            continue
        try:
            enhanced = rescore_experiment(filepath, dry_run=args.dry_run)
            if enhanced:
                all_enhanced[Path(filepath).stem] = enhanced
        except Exception as e:
            print(f"  Error: {e}")

    if args.dry_run:
        return

    # Save combined clinical scoring report
    output = {
        'title': 'Clinical Forecast Metrics (Approximate)',
        'note': 'MARD and Clarke zones approximated from stored MAE values. '
                'For exact metrics, re-run models with compute_clinical_forecast_metrics().',
        'population_glucose_mean_mgdl': POPULATION_GLUCOSE_MEAN,
        'population_glucose_std_mgdl': POPULATION_GLUCOSE_STD,
        'experiments': all_enhanced,
    }

    outpath = RESULTS_DIR / 'clinical_forecast_scoring.json'
    with open(outpath, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nSaved: {outpath}")

    # Summary table
    print(f"\n{'='*70}")
    print(f"  CLINICAL SCORING SUMMARY")
    print(f"{'='*70}")
    print(f"  {'Experiment':<35s} {'MAE':>8s} {'MARD%':>8s} {'Clarke A+B':>12s}")
    print(f"  {'-'*35} {'-'*8} {'-'*8} {'-'*12}")
    for exp_name, variants in all_enhanced.items():
        if isinstance(variants, dict) and 'mae_mgdl' in variants:
            mae = variants['mae_mgdl']
            mard = variants.get('mard_approx_pct', 0)
            ab = variants.get('clarke_approx', {}).get('zone_AB_pct', 0) * 100
            print(f"  {exp_name:<35s} {mae:>7.1f} {mard:>7.1f}% {ab:>10.1f}%")
        else:
            for vname, vdata in variants.items():
                if not isinstance(vdata, dict):
                    continue
                mae = vdata.get('mae_mgdl', 0)
                mard = vdata.get('mard_approx_pct', 0)
                ab = vdata.get('clarke_approx', {}).get('zone_AB_pct', 0)
                if isinstance(ab, float):
                    ab *= 100
                else:
                    ab = 0
                label = f"{exp_name}/{vname}"
                print(f"  {label:<35s} {mae:>7.1f} {mard:>7.1f}% {ab:>10.1f}%")


if __name__ == '__main__':
    main()
