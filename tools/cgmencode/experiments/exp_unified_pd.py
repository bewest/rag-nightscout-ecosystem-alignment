#!/usr/bin/env python3
"""EXP-2529: Unified pharmacodynamics model in glucose forecasting.

Tests whether encoding power-law ISF, two-component DIA, and mean
reversion into Ridge features improves R² beyond the 0.61 ceiling.

Findings integrated:
  EXP-2511  Power-law ISF: ISF(dose) = ISF_base × dose^(-0.9)
  EXP-2525  Two-component DIA: fast (τ=0.8h) + persistent HGP suppression
  EXP-2526  Mean reversion: 75% of 130-180 corrections rebound; threshold ≈ 166

Sub-experiments:
  EXP-2529a  Feature engineering (5 new PD features)
  EXP-2529b  Ridge comparison: baseline 8-feature vs enhanced 13-feature
  EXP-2529c  Ablation: marginal R² contribution of each PD feature
"""

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold
from sklearn.metrics import r2_score

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'externals' / 'experiments'
DATA_PATH = Path(__file__).resolve().parent.parent.parent.parent / 'externals' / 'ns-parquet' / 'training' / 'grid.parquet'

HORIZONS = {'h12': 12, 'h30': 30, 'h60': 60}  # steps (5 min each)
ALPHA = 1.0  # Ridge regularization
N_FOLDS = 5
MIN_ROWS_PER_PATIENT = 500  # skip patients with too few valid rows
TAU_FAST_HOURS = 0.8
PERSISTENT_WINDOW_STEPS = 144  # 12h in 5-min steps
POWERLAW_WINDOW_STEPS = 48    # 4h in 5-min steps
CORRECTION_WINDOW_STEPS = 24  # 2h in 5-min steps
MIN_CORRECTION_BOLUS = 0.3    # U, consistent with existing experiments

BASELINE_FEATURES = [
    'glucose', 'glucose_roc', 'glucose_accel',
    'iob', 'cob', 'net_basal', 'bolus_recent', 'glucose_vs_target',
]

PD_FEATURES = [
    'iob_fast', 'iob_persistent', 'bolus_powerlaw',
    'correction_rebound_risk', 'correction_safe_zone',
]


def load_grid():
    """Load grid parquet and select relevant columns."""
    cols = [
        'patient_id', 'time', 'glucose', 'glucose_roc', 'glucose_accel',
        'iob', 'cob', 'net_basal', 'bolus', 'bolus_smb',
        'time_since_bolus_min', 'scheduled_isf', 'glucose_vs_target',
    ]
    df = pd.read_parquet(DATA_PATH, columns=cols)
    df = df.sort_values(['patient_id', 'time']).reset_index(drop=True)
    return df


def engineer_features(pdf):
    """Add the 5 PD features to a per-patient dataframe (sorted by time).

    Returns a copy with new columns added.
    """
    df = pdf.copy()

    # --- bolus_recent: any bolus in last 2h (used in baseline) ---
    bolus = df['bolus'].fillna(0.0).values
    df['bolus_recent'] = pd.Series(bolus).rolling(
        window=CORRECTION_WINDOW_STEPS, min_periods=1
    ).sum().values

    # --- 1. iob_fast: IOB × exp(-time_since_bolus / (τ_fast in minutes)) ---
    tsb = df['time_since_bolus_min'].fillna(9999.0).values
    tau_min = TAU_FAST_HOURS * 60.0
    iob = df['iob'].fillna(0.0).values
    df['iob_fast'] = iob * np.exp(-tsb / tau_min)

    # --- 2. iob_persistent: total bolus in last 12h (scaled HGP suppression) ---
    df['iob_persistent'] = pd.Series(bolus).rolling(
        window=PERSISTENT_WINDOW_STEPS, min_periods=1
    ).sum().values

    # --- 3. bolus_powerlaw: sum of bolus^0.1 in last 4h ---
    bolus_pl = np.where(bolus > 0, np.power(bolus, 0.1), 0.0)
    df['bolus_powerlaw'] = pd.Series(bolus_pl).rolling(
        window=POWERLAW_WINDOW_STEPS, min_periods=1
    ).sum().values

    # --- 4. correction_rebound_risk: BG in 130-180 AND correction in last 2h ---
    g = df['glucose'].values
    correction_flag = pd.Series(
        np.where(bolus >= MIN_CORRECTION_BOLUS, 1.0, 0.0)
    ).rolling(window=CORRECTION_WINDOW_STEPS, min_periods=1).max().values
    in_rebound_zone = (g >= 130) & (g <= 180)
    df['correction_rebound_risk'] = np.where(
        in_rebound_zone & (correction_flag > 0), 1.0, 0.0
    )

    # --- 5. correction_safe_zone: BG > 166 AND correction in last 2h ---
    above_threshold = g > 166
    df['correction_safe_zone'] = np.where(
        above_threshold & (correction_flag > 0), 1.0, 0.0
    )

    return df


def build_targets(df, horizon_steps):
    """Create target column: glucose shifted forward by horizon_steps."""
    return df.groupby('patient_id')['glucose'].shift(-horizon_steps)


def run_ridge_cv(X, y, n_folds=N_FOLDS, alpha=ALPHA):
    """Run Ridge with k-fold CV; return per-fold R² and overall R²."""
    mask = np.isfinite(X).all(axis=1) & np.isfinite(y)
    X_clean, y_clean = X[mask], y[mask]

    if len(X_clean) < n_folds * 20:
        return None

    kf = KFold(n_splits=n_folds, shuffle=True, random_state=42)
    fold_r2 = []
    y_pred_all = np.full(len(y_clean), np.nan)

    for train_idx, test_idx in kf.split(X_clean):
        model = Ridge(alpha=alpha)
        model.fit(X_clean[train_idx], y_clean[train_idx])
        pred = model.predict(X_clean[test_idx])
        fold_r2.append(r2_score(y_clean[test_idx], pred))
        y_pred_all[test_idx] = pred

    overall_r2 = r2_score(y_clean[~np.isnan(y_pred_all)],
                          y_pred_all[~np.isnan(y_pred_all)])
    return {
        'r2_cv_mean': float(np.mean(fold_r2)),
        'r2_cv_std': float(np.std(fold_r2)),
        'r2_overall': float(overall_r2),
        'n_samples': int(len(X_clean)),
        'fold_r2': [float(r) for r in fold_r2],
    }


def exp_2529b_ridge_comparison(df):
    """Compare baseline (8 features) vs enhanced (8+5 features) Ridge."""
    patients = df['patient_id'].unique()
    all_features = BASELINE_FEATURES + PD_FEATURES

    results = {h: [] for h in HORIZONS}

    for pid in patients:
        pdf = df[df['patient_id'] == pid]
        if len(pdf) < MIN_ROWS_PER_PATIENT:
            continue

        for hname, hsteps in HORIZONS.items():
            target = build_targets(pdf, hsteps).values

            X_base = pdf[BASELINE_FEATURES].values
            X_enh = pdf[all_features].values

            res_base = run_ridge_cv(X_base, target)
            res_enh = run_ridge_cv(X_enh, target)

            if res_base is None or res_enh is None:
                continue

            delta = res_enh['r2_cv_mean'] - res_base['r2_cv_mean']
            results[hname].append({
                'patient': str(pid),
                'baseline_r2': res_base['r2_cv_mean'],
                'enhanced_r2': res_enh['r2_cv_mean'],
                'delta_r2': delta,
                'n_samples': res_base['n_samples'],
                'baseline_detail': res_base,
                'enhanced_detail': res_enh,
            })

    return results


def exp_2529c_ablation(df):
    """Add PD features one at a time to measure marginal R² contribution."""
    patients = df['patient_id'].unique()

    results = {h: {feat: [] for feat in PD_FEATURES} for h in HORIZONS}

    for pid in patients:
        pdf = df[df['patient_id'] == pid]
        if len(pdf) < MIN_ROWS_PER_PATIENT:
            continue

        for hname, hsteps in HORIZONS.items():
            target = build_targets(pdf, hsteps).values
            X_base = pdf[BASELINE_FEATURES].values
            res_base = run_ridge_cv(X_base, target)
            if res_base is None:
                continue

            for feat in PD_FEATURES:
                feat_col = pdf[feat].values.reshape(-1, 1)
                X_aug = np.hstack([X_base, feat_col])
                res_aug = run_ridge_cv(X_aug, target)
                if res_aug is None:
                    continue

                results[hname][feat].append({
                    'patient': str(pid),
                    'baseline_r2': res_base['r2_cv_mean'],
                    'augmented_r2': res_aug['r2_cv_mean'],
                    'marginal_r2': res_aug['r2_cv_mean'] - res_base['r2_cv_mean'],
                })

    return results


def summarize_comparison(comp_results):
    """Build summary table from comparison results."""
    summary = {}
    for hname, patient_results in comp_results.items():
        if not patient_results:
            summary[hname] = {'n': 0}
            continue
        base_r2s = [r['baseline_r2'] for r in patient_results]
        enh_r2s = [r['enhanced_r2'] for r in patient_results]
        deltas = [r['delta_r2'] for r in patient_results]
        wins = sum(1 for d in deltas if d > 0)
        summary[hname] = {
            'n': len(patient_results),
            'baseline_r2_mean': float(np.mean(base_r2s)),
            'baseline_r2_std': float(np.std(base_r2s)),
            'enhanced_r2_mean': float(np.mean(enh_r2s)),
            'enhanced_r2_std': float(np.std(enh_r2s)),
            'delta_r2_mean': float(np.mean(deltas)),
            'delta_r2_std': float(np.std(deltas)),
            'win_rate': float(wins / len(deltas)),
            'wins': wins,
            'losses': len(deltas) - wins,
        }
    return summary


def summarize_ablation(abl_results):
    """Build summary table from ablation results."""
    summary = {}
    for hname, feat_results in abl_results.items():
        summary[hname] = {}
        for feat, patient_results in feat_results.items():
            if not patient_results:
                summary[hname][feat] = {'n': 0}
                continue
            marginals = [r['marginal_r2'] for r in patient_results]
            wins = sum(1 for m in marginals if m > 0)
            summary[hname][feat] = {
                'n': len(patient_results),
                'marginal_r2_mean': float(np.mean(marginals)),
                'marginal_r2_std': float(np.std(marginals)),
                'win_rate': float(wins / len(marginals)),
            }
    return summary


def print_results(comp_summary, abl_summary, comp_results):
    """Print formatted results tables."""
    print('\n' + '=' * 80)
    print('EXP-2529b: Ridge Comparison — Baseline (8 feat) vs Enhanced (13 feat)')
    print('=' * 80)

    header = f'{"Horizon":<8} {"N":>3} {"Base R²":>10} {"Enh R²":>10} {"ΔR²":>10} {"Win%":>6}'
    print(header)
    print('-' * len(header))
    for hname in HORIZONS:
        s = comp_summary[hname]
        if s['n'] == 0:
            print(f'{hname:<8} {"—":>3}')
            continue
        print(f'{hname:<8} {s["n"]:>3} '
              f'{s["baseline_r2_mean"]:>10.4f} '
              f'{s["enhanced_r2_mean"]:>10.4f} '
              f'{s["delta_r2_mean"]:>+10.4f} '
              f'{s["win_rate"]*100:>5.0f}%')

    # Per-patient detail for h60
    print('\n' + '-' * 80)
    print('Per-Patient Detail (h60):')
    print(f'{"Patient":<12} {"Base R²":>10} {"Enh R²":>10} {"ΔR²":>10} {"N":>8}')
    print('-' * 52)
    for r in sorted(comp_results.get('h60', []), key=lambda x: x['patient']):
        marker = '✓' if r['delta_r2'] > 0 else '✗'
        print(f'{r["patient"]:<12} {r["baseline_r2"]:>10.4f} '
              f'{r["enhanced_r2"]:>10.4f} {r["delta_r2"]:>+10.4f} '
              f'{r["n_samples"]:>7} {marker}')

    print('\n' + '=' * 80)
    print('EXP-2529c: Ablation — Marginal R² Contribution of Each PD Feature')
    print('=' * 80)
    for hname in HORIZONS:
        print(f'\n  {hname} ({HORIZONS[hname]*5} min):')
        header2 = f'  {"Feature":<28} {"ΔR²":>10} {"±σ":>8} {"Win%":>6}'
        print(header2)
        print('  ' + '-' * len(header2.strip()))
        for feat in PD_FEATURES:
            s = abl_summary[hname].get(feat, {'n': 0})
            if s['n'] == 0:
                continue
            print(f'  {feat:<28} {s["marginal_r2_mean"]:>+10.5f} '
                  f'{s["marginal_r2_std"]:>8.5f} '
                  f'{s["win_rate"]*100:>5.0f}%')


def main():
    t0 = time.time()

    print('EXP-2529: Unified Pharmacodynamics Model in Glucose Forecasting')
    print(f'Loading data from {DATA_PATH} ...')
    df = load_grid()
    print(f'  Loaded {len(df):,} rows, {df["patient_id"].nunique()} patients')

    print('Engineering PD features ...')
    parts = []
    for pid, pdf in df.groupby('patient_id'):
        part = engineer_features(pdf)
        parts.append(part)
    df = pd.concat(parts, ignore_index=True)

    # Fill remaining NaNs in feature columns with 0 for Ridge
    all_features = BASELINE_FEATURES + PD_FEATURES
    for col in all_features:
        if col in df.columns:
            df[col] = df[col].fillna(0.0)

    print(f'  Feature matrix ready: {len(df):,} rows × {len(all_features)} features')

    # Quick feature summary
    print('\n  PD Feature Summary:')
    for feat in PD_FEATURES:
        vals = df[feat]
        nz = (vals != 0).sum()
        print(f'    {feat:<28} mean={vals.mean():>8.4f}  '
              f'std={vals.std():>8.4f}  nonzero={nz:>7,} ({nz/len(df)*100:.1f}%)')

    # --- EXP-2529b: Ridge Comparison ---
    print('\nRunning EXP-2529b: Ridge comparison ...')
    comp_results = exp_2529b_ridge_comparison(df)
    comp_summary = summarize_comparison(comp_results)

    # --- EXP-2529c: Ablation ---
    print('Running EXP-2529c: Ablation study ...')
    abl_results = exp_2529c_ablation(df)
    abl_summary = summarize_ablation(abl_results)

    elapsed = round(time.time() - t0, 1)

    # --- Print ---
    print_results(comp_summary, abl_summary, comp_results)

    print(f'\nCompleted in {elapsed}s')

    # --- Save ---
    output = {
        'experiment': 'EXP-2529',
        'name': 'Unified pharmacodynamics model in glucose forecasting',
        'status': 'pass',
        'hypothesis': (
            'Encoding power-law ISF, two-component DIA, and mean reversion '
            'as Ridge features improves R² beyond the 0.61 h60 ceiling.'
        ),
        'config': {
            'horizons': {k: v * 5 for k, v in HORIZONS.items()},
            'alpha': ALPHA,
            'n_folds': N_FOLDS,
            'tau_fast_hours': TAU_FAST_HOURS,
            'persistent_window_hours': PERSISTENT_WINDOW_STEPS * 5 / 60,
            'powerlaw_window_hours': POWERLAW_WINDOW_STEPS * 5 / 60,
            'correction_window_hours': CORRECTION_WINDOW_STEPS * 5 / 60,
            'min_correction_bolus': MIN_CORRECTION_BOLUS,
            'baseline_features': BASELINE_FEATURES,
            'pd_features': PD_FEATURES,
        },
        'results': {
            'comparison': {
                'summary': comp_summary,
                'per_patient': comp_results,
            },
            'ablation': {
                'summary': abl_summary,
                'per_patient': abl_results,
            },
        },
        'elapsed_seconds': elapsed,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / 'exp-2529_unified_pd.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f'Results saved to {out_path}')


if __name__ == '__main__':
    main()
