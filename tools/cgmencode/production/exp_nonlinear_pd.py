#!/usr/bin/env python3
"""EXP-2531: Nonlinear PD Forecasting with GBM.

Tests whether gradient boosted machines capture nonlinear interactions
in pharmacodynamic features that Ridge regression cannot exploit.

Based on EXP-2529 findings:
  - Power-law ISF + two-component DIA + mean reversion features
    improved Ridge R² by +0.011 at h60 (100% win rate)
  - But Ridge is linear; GBM should exploit nonlinear interactions

Sub-experiments:
  EXP-2531a  GBM with PD features vs baseline (temporal CV)
  EXP-2531b  Feature importance ranking (gain-based)
  EXP-2531c  2×2 comparison: {Ridge, GBM} × {baseline, +PD features}
"""

import json
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import r2_score

warnings.filterwarnings('ignore', category=UserWarning, module='sklearn')
warnings.filterwarnings('ignore', message='.*ill-conditioned.*')

try:
    import lightgbm as lgb
    USE_LIGHTGBM = True
except ImportError:
    from sklearn.ensemble import GradientBoostingRegressor
    USE_LIGHTGBM = False

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
RESULTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'externals' / 'experiments'
DATA_PATH = Path(__file__).resolve().parent.parent.parent.parent / 'externals' / 'ns-parquet' / 'training' / 'grid.parquet'

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
HORIZONS = {'h12': 12, 'h30': 30, 'h60': 60}  # steps (5 min each)
ALPHA = 1.0  # Ridge regularization
N_FOLDS = 5
MIN_ROWS_PER_PATIENT = 500
TAU_FAST_HOURS = 0.8
PERSISTENT_WINDOW_STEPS = 144  # 12h in 5-min steps
POWERLAW_WINDOW_STEPS = 48     # 4h in 5-min steps
CORRECTION_WINDOW_STEPS = 24   # 2h in 5-min steps
MIN_CORRECTION_BOLUS = 0.3     # U

# 5 baseline features (user spec: sgv, iob, cob, net_flux, bgi)
BASELINE_FEATURES = ['glucose', 'iob', 'cob', 'net_basal', 'glucose_roc']

# 4 PD features
PD_FEATURES = [
    'bolus_powerlaw', 'iob_persistent',
    'correction_rebound_risk', 'iob_fast',
]

# GBM hyperparameters
GBM_PARAMS = {
    'n_estimators': 200,
    'max_depth': 5,
    'learning_rate': 0.1,
    'min_samples_leaf': 20,
}


def load_grid():
    """Load grid parquet with relevant columns."""
    cols = [
        'patient_id', 'time', 'glucose', 'glucose_roc',
        'iob', 'cob', 'net_basal', 'bolus', 'bolus_smb',
        'time_since_bolus_min',
    ]
    df = pd.read_parquet(DATA_PATH, columns=cols)
    df = df.sort_values(['patient_id', 'time']).reset_index(drop=True)
    return df


def engineer_features(pdf):
    """Add the 4 PD features to a per-patient dataframe (sorted by time)."""
    df = pdf.copy()
    bolus = df['bolus'].fillna(0.0).values

    # 1. bolus_powerlaw: sum of bolus^0.1 in last 4h
    bolus_pl = np.where(bolus > 0, np.power(bolus, 0.1), 0.0)
    df['bolus_powerlaw'] = pd.Series(bolus_pl).rolling(
        window=POWERLAW_WINDOW_STEPS, min_periods=1
    ).sum().values

    # 2. iob_persistent: total bolus in last 12h (HGP suppression proxy)
    df['iob_persistent'] = pd.Series(bolus).rolling(
        window=PERSISTENT_WINDOW_STEPS, min_periods=1
    ).sum().values

    # 3. correction_rebound_risk: glucose in [130,180] AND correction in last 2h
    g = df['glucose'].values
    correction_flag = pd.Series(
        np.where(bolus >= MIN_CORRECTION_BOLUS, 1.0, 0.0)
    ).rolling(window=CORRECTION_WINDOW_STEPS, min_periods=1).max().values
    in_rebound_zone = (g >= 130) & (g <= 180)
    df['correction_rebound_risk'] = np.where(
        in_rebound_zone & (correction_flag > 0), 1.0, 0.0
    )

    # 4. iob_fast: IOB × exp(-time_since_bolus / tau_fast)
    tsb = df['time_since_bolus_min'].fillna(9999.0).values
    tau_min = TAU_FAST_HOURS * 60.0
    iob = df['iob'].fillna(0.0).values
    df['iob_fast'] = iob * np.exp(-tsb / tau_min)

    return df


def build_targets(df, horizon_steps):
    """Create target: glucose shifted forward by horizon_steps."""
    return df.groupby('patient_id')['glucose'].shift(-horizon_steps)


def _clean_Xy(X, y):
    """Remove rows with NaN/inf in X or y."""
    mask = np.isfinite(X).all(axis=1) & np.isfinite(y)
    return X[mask], y[mask], mask


def run_temporal_cv(model_factory, X, y, feature_names=None, n_folds=N_FOLDS):
    """Run model with TimeSeriesSplit CV (no shuffling). Returns metrics dict."""
    X_clean, y_clean, _ = _clean_Xy(X, y)

    if len(X_clean) < n_folds * 50:
        return None

    tscv = TimeSeriesSplit(n_splits=n_folds)
    fold_r2 = []
    y_pred_all = np.full(len(y_clean), np.nan)

    for train_idx, test_idx in tscv.split(X_clean):
        model = model_factory()
        X_train = pd.DataFrame(X_clean[train_idx], columns=feature_names) if feature_names else X_clean[train_idx]
        X_test = pd.DataFrame(X_clean[test_idx], columns=feature_names) if feature_names else X_clean[test_idx]
        model.fit(X_train, y_clean[train_idx])
        pred = model.predict(X_test)
        fold_r2.append(r2_score(y_clean[test_idx], pred))
        y_pred_all[test_idx] = pred

    valid = ~np.isnan(y_pred_all)
    overall_r2 = r2_score(y_clean[valid], y_pred_all[valid])

    return {
        'r2_cv_mean': float(np.mean(fold_r2)),
        'r2_cv_std': float(np.std(fold_r2)),
        'r2_overall': float(overall_r2),
        'n_samples': int(len(X_clean)),
        'fold_r2': [float(r) for r in fold_r2],
    }


def run_temporal_cv_with_importance(model_factory, X, y, feature_names,
                                    n_folds=N_FOLDS):
    """Like run_temporal_cv but also returns averaged feature importances."""
    X_clean, y_clean, _ = _clean_Xy(X, y)

    if len(X_clean) < n_folds * 50:
        return None, None

    tscv = TimeSeriesSplit(n_splits=n_folds)
    fold_r2 = []
    y_pred_all = np.full(len(y_clean), np.nan)
    importance_acc = np.zeros(X_clean.shape[1])

    for train_idx, test_idx in tscv.split(X_clean):
        model = model_factory()
        X_train = pd.DataFrame(X_clean[train_idx], columns=feature_names)
        X_test = pd.DataFrame(X_clean[test_idx], columns=feature_names)
        model.fit(X_train, y_clean[train_idx])
        pred = model.predict(X_test)
        fold_r2.append(r2_score(y_clean[test_idx], pred))
        y_pred_all[test_idx] = pred

        if hasattr(model, 'feature_importances_'):
            importance_acc += model.feature_importances_
        elif USE_LIGHTGBM and hasattr(model, 'feature_importance'):
            importance_acc += model.feature_importance(importance_type='gain')

    valid = ~np.isnan(y_pred_all)
    overall_r2 = r2_score(y_clean[valid], y_pred_all[valid])

    importance_avg = importance_acc / n_folds
    total = importance_avg.sum()
    if total > 0:
        importance_pct = importance_avg / total
    else:
        importance_pct = importance_avg

    importance_dict = {
        name: float(importance_pct[i])
        for i, name in enumerate(feature_names)
    }

    metrics = {
        'r2_cv_mean': float(np.mean(fold_r2)),
        'r2_cv_std': float(np.std(fold_r2)),
        'r2_overall': float(overall_r2),
        'n_samples': int(len(X_clean)),
        'fold_r2': [float(r) for r in fold_r2],
    }
    return metrics, importance_dict


# ---------------------------------------------------------------------------
# Model factories
# ---------------------------------------------------------------------------
def make_ridge():
    return Ridge(alpha=ALPHA)


def make_gbm():
    if USE_LIGHTGBM:
        return lgb.LGBMRegressor(
            n_estimators=GBM_PARAMS['n_estimators'],
            max_depth=GBM_PARAMS['max_depth'],
            learning_rate=GBM_PARAMS['learning_rate'],
            min_child_samples=GBM_PARAMS['min_samples_leaf'],
            verbosity=-1,
            n_jobs=-1,
        )
    else:
        return GradientBoostingRegressor(
            n_estimators=GBM_PARAMS['n_estimators'],
            max_depth=GBM_PARAMS['max_depth'],
            learning_rate=GBM_PARAMS['learning_rate'],
            min_samples_leaf=GBM_PARAMS['min_samples_leaf'],
        )


# ---------------------------------------------------------------------------
# EXP-2531c: 2×2 comparison
# ---------------------------------------------------------------------------
def run_2x2_comparison(df):
    """Run the 2×2 design: {Ridge, GBM} × {baseline, +PD} across all patients/horizons."""
    patients = sorted(df['patient_id'].unique())
    all_features = BASELINE_FEATURES + PD_FEATURES

    configs = {
        'ridge_base': (make_ridge, BASELINE_FEATURES),
        'ridge_pd':   (make_ridge, all_features),
        'gbm_base':   (make_gbm,   BASELINE_FEATURES),
        'gbm_pd':     (make_gbm,   all_features),
    }

    results = {h: {cfg: [] for cfg in configs} for h in HORIZONS}
    importance_results = {h: [] for h in HORIZONS}  # EXP-2531b

    n_patients = len(patients)
    for i, pid in enumerate(patients):
        pdf = df[df['patient_id'] == pid]
        if len(pdf) < MIN_ROWS_PER_PATIENT:
            continue

        print(f'  Patient {pid} ({i+1}/{n_patients}, {len(pdf):,} rows)')

        for hname, hsteps in HORIZONS.items():
            target = build_targets(pdf, hsteps).values

            for cfg_name, (factory, feat_list) in configs.items():
                X = pdf[feat_list].values
                y = target

                if cfg_name == 'gbm_pd':
                    # Collect feature importance for EXP-2531b
                    metrics, imp = run_temporal_cv_with_importance(
                        factory, X, y, feat_list
                    )
                    if metrics is not None and imp is not None:
                        importance_results[hname].append({
                            'patient': str(pid),
                            'importance': imp,
                        })
                else:
                    metrics = run_temporal_cv(factory, X, y,
                                             feature_names=feat_list)

                if metrics is not None:
                    results[hname][cfg_name].append({
                        'patient': str(pid),
                        'r2': metrics['r2_cv_mean'],
                        'r2_std': metrics['r2_cv_std'],
                        'n_samples': metrics['n_samples'],
                        'detail': metrics,
                    })

    return results, importance_results


# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------
def summarize_2x2(results):
    """Build summary across the 2×2 design."""
    summary = {}
    for hname, cfg_results in results.items():
        summary[hname] = {}
        for cfg_name, patient_results in cfg_results.items():
            if not patient_results:
                summary[hname][cfg_name] = {'n': 0}
                continue
            r2s = [r['r2'] for r in patient_results]
            summary[hname][cfg_name] = {
                'n': len(patient_results),
                'r2_mean': float(np.mean(r2s)),
                'r2_std': float(np.std(r2s)),
                'r2_median': float(np.median(r2s)),
            }
    return summary


def compute_deltas(results):
    """Compute pairwise deltas for the key comparisons."""
    deltas = {}
    comparisons = [
        ('feature_effect_ridge', 'ridge_base', 'ridge_pd', 'Ridge: +PD features'),
        ('feature_effect_gbm',   'gbm_base',   'gbm_pd',   'GBM: +PD features'),
        ('model_effect_base',    'ridge_base',  'gbm_base', 'Base feat: GBM vs Ridge'),
        ('model_effect_pd',      'ridge_pd',    'gbm_pd',   'PD feat: GBM vs Ridge'),
    ]

    for hname, cfg_results in results.items():
        deltas[hname] = {}
        for comp_key, cfg_a, cfg_b, label in comparisons:
            pa = {r['patient']: r['r2'] for r in cfg_results[cfg_a]}
            pb = {r['patient']: r['r2'] for r in cfg_results[cfg_b]}
            common = sorted(set(pa) & set(pb))
            if not common:
                deltas[hname][comp_key] = {'n': 0, 'label': label}
                continue
            d = [pb[p] - pa[p] for p in common]
            wins = sum(1 for x in d if x > 0)
            deltas[hname][comp_key] = {
                'label': label,
                'n': len(common),
                'delta_mean': float(np.mean(d)),
                'delta_std': float(np.std(d)),
                'delta_median': float(np.median(d)),
                'win_rate': float(wins / len(common)),
                'wins': wins,
                'losses': len(common) - wins,
            }
    return deltas


def summarize_importance(importance_results):
    """Average feature importance across patients."""
    summary = {}
    for hname, patient_imps in importance_results.items():
        if not patient_imps:
            summary[hname] = {}
            continue
        all_feats = list(patient_imps[0]['importance'].keys())
        agg = {f: [] for f in all_feats}
        for pi in patient_imps:
            for f in all_feats:
                agg[f].append(pi['importance'].get(f, 0.0))
        summary[hname] = {
            f: {
                'mean': float(np.mean(agg[f])),
                'std': float(np.std(agg[f])),
            }
            for f in all_feats
        }
    return summary


# ---------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------
def print_results(summary_2x2, deltas, imp_summary, results):
    """Print formatted result tables."""
    cfg_labels = {
        'ridge_base': 'Ridge-Base',
        'ridge_pd':   'Ridge+PD',
        'gbm_base':   'GBM-Base',
        'gbm_pd':     'GBM+PD',
    }

    # --- EXP-2531c: 2×2 R² table ---
    print('\n' + '=' * 80)
    print('EXP-2531c: 2×2 Comparison — R² by Model × Feature Set')
    print('=' * 80)

    header = (f'{"Horizon":<8} '
              f'{"Ridge-Base":>12} {"Ridge+PD":>12} '
              f'{"GBM-Base":>12} {"GBM+PD":>12}')
    print(header)
    print('-' * len(header))
    for hname in HORIZONS:
        parts = [f'{hname:<8}']
        for cfg in ['ridge_base', 'ridge_pd', 'gbm_base', 'gbm_pd']:
            s = summary_2x2[hname].get(cfg, {'n': 0})
            if s['n'] == 0:
                parts.append(f'{"—":>12}')
            else:
                parts.append(f'{s["r2_mean"]:>12.4f}')
        print(' '.join(parts))

    # --- Delta table ---
    print('\n' + '=' * 80)
    print('EXP-2531c: Pairwise ΔR² (column B minus column A)')
    print('=' * 80)

    comp_keys = ['feature_effect_ridge', 'feature_effect_gbm',
                 'model_effect_base', 'model_effect_pd']
    header2 = f'{"Horizon":<8} {"Comparison":<28} {"ΔR²":>10} {"±σ":>8} {"Win%":>6} {"N":>4}'
    print(header2)
    print('-' * len(header2))
    for hname in HORIZONS:
        for ck in comp_keys:
            d = deltas[hname].get(ck, {'n': 0})
            if d['n'] == 0:
                continue
            print(f'{hname:<8} {d["label"]:<28} '
                  f'{d["delta_mean"]:>+10.4f} '
                  f'{d["delta_std"]:>8.4f} '
                  f'{d["win_rate"]*100:>5.0f}% '
                  f'{d["n"]:>4}')

    # --- Per-patient detail for h60 ---
    print('\n' + '-' * 80)
    print('Per-Patient Detail (h60):')
    hname = 'h60'
    cfg_order = ['ridge_base', 'ridge_pd', 'gbm_base', 'gbm_pd']
    patient_data = {}
    for cfg in cfg_order:
        for r in results.get(hname, {}).get(cfg, []):
            patient_data.setdefault(r['patient'], {})[cfg] = r['r2']

    header3 = (f'{"Patient":<12} '
               f'{"Ridge-B":>9} {"Ridge+PD":>9} '
               f'{"GBM-B":>9} {"GBM+PD":>9} '
               f'{"Best":>10}')
    print(header3)
    print('-' * len(header3))
    for pid in sorted(patient_data):
        pd_row = patient_data[pid]
        parts = [f'{pid:<12}']
        best_val = -999
        best_name = '—'
        for cfg in cfg_order:
            v = pd_row.get(cfg)
            if v is not None:
                parts.append(f'{v:>9.4f}')
                if v > best_val:
                    best_val = v
                    best_name = cfg_labels[cfg]
            else:
                parts.append(f'{"—":>9}')
        parts.append(f'{best_name:>10}')
        print(' '.join(parts))

    # --- EXP-2531b: Feature importance ---
    print('\n' + '=' * 80)
    print('EXP-2531b: GBM+PD Feature Importance (gain-based, % of total)')
    print('=' * 80)
    all_features = BASELINE_FEATURES + PD_FEATURES
    for hname in HORIZONS:
        print(f'\n  {hname} ({HORIZONS[hname]*5} min):')
        header4 = f'  {"Feature":<28} {"Importance%":>12} {"±σ":>8}'
        print(header4)
        print('  ' + '-' * len(header4.strip()))

        if hname not in imp_summary or not imp_summary[hname]:
            print('  (no data)')
            continue

        ranked = sorted(imp_summary[hname].items(),
                        key=lambda x: x[1]['mean'], reverse=True)
        for feat, stats in ranked:
            is_pd = '★' if feat in PD_FEATURES else ' '
            print(f'  {is_pd} {feat:<26} {stats["mean"]*100:>11.2f}% '
                  f'{stats["std"]*100:>7.2f}%')


def main():
    t0 = time.time()

    engine_name = 'LightGBM' if USE_LIGHTGBM else 'sklearn.GradientBoostingRegressor'
    print(f'EXP-2531: Nonlinear PD Forecasting with GBM ({engine_name})')
    print(f'Loading data from {DATA_PATH} ...')
    df = load_grid()
    print(f'  Loaded {len(df):,} rows, {df["patient_id"].nunique()} patients')

    print('Engineering PD features ...')
    parts = []
    for pid, pdf in df.groupby('patient_id'):
        parts.append(engineer_features(pdf))
    df = pd.concat(parts, ignore_index=True)

    all_features = BASELINE_FEATURES + PD_FEATURES
    for col in all_features:
        if col in df.columns:
            df[col] = df[col].fillna(0.0)

    print(f'  Feature matrix: {len(df):,} rows × {len(all_features)} features')
    print(f'  Temporal CV: {N_FOLDS}-fold TimeSeriesSplit (no shuffling)')
    print(f'  GBM params: {GBM_PARAMS}')

    print('\n  PD Feature Summary:')
    for feat in PD_FEATURES:
        vals = df[feat]
        nz = (vals != 0).sum()
        print(f'    {feat:<28} mean={vals.mean():>8.4f}  '
              f'std={vals.std():>8.4f}  nonzero={nz:>7,} ({nz/len(df)*100:.1f}%)')

    # --- Run 2×2 comparison (covers EXP-2531a, b, c) ---
    print('\nRunning 2×2 comparison ({Ridge,GBM} × {base,+PD}) ...')
    results, importance_results = run_2x2_comparison(df)

    summary_2x2 = summarize_2x2(results)
    deltas = compute_deltas(results)
    imp_summary = summarize_importance(importance_results)

    elapsed = round(time.time() - t0, 1)

    # --- Print ---
    print_results(summary_2x2, deltas, imp_summary, results)
    print(f'\nCompleted in {elapsed}s')

    # --- Determine pass/fail ---
    # Pass if GBM+PD beats Ridge+PD at h60
    d_model_pd = deltas.get('h60', {}).get('model_effect_pd', {})
    status = 'pass' if d_model_pd.get('delta_mean', 0) > 0 else 'neutral'

    # --- Save ---
    output = {
        'experiment': 'EXP-2531',
        'name': 'Nonlinear PD forecasting with GBM',
        'status': status,
        'hypothesis': (
            'GBM captures nonlinear interactions (power-law ISF saturation, '
            'IOB persistence × BG level, conditional rebound probability) '
            'that Ridge cannot exploit, yielding higher R² on PD features.'
        ),
        'config': {
            'horizons': {k: v * 5 for k, v in HORIZONS.items()},
            'gbm_engine': engine_name,
            'gbm_params': GBM_PARAMS,
            'ridge_alpha': ALPHA,
            'n_folds': N_FOLDS,
            'cv_method': 'TimeSeriesSplit (temporal, no shuffling)',
            'tau_fast_hours': TAU_FAST_HOURS,
            'persistent_window_hours': PERSISTENT_WINDOW_STEPS * 5 / 60,
            'powerlaw_window_hours': POWERLAW_WINDOW_STEPS * 5 / 60,
            'correction_window_hours': CORRECTION_WINDOW_STEPS * 5 / 60,
            'min_correction_bolus': MIN_CORRECTION_BOLUS,
            'baseline_features': BASELINE_FEATURES,
            'pd_features': PD_FEATURES,
        },
        'results': {
            'summary_2x2': summary_2x2,
            'deltas': deltas,
            'feature_importance': imp_summary,
            'per_patient': {
                h: {cfg: cfg_results
                    for cfg, cfg_results in cfg_data.items()}
                for h, cfg_data in results.items()
            },
        },
        'elapsed_seconds': elapsed,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / 'exp-2531_nonlinear_pd.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f'Results saved to {out_path}')


if __name__ == '__main__':
    main()
