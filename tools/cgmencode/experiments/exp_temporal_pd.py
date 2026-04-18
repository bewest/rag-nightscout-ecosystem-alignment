#!/usr/bin/env python3
"""EXP-2532: Temporal-Robust PD Feature Redesign.

EXP-2531 showed that raw PD features (power-law ISF, persistent IOB,
rebound risk) DEGRADE R² under temporal CV despite helping with shuffled
CV.  This means those features leak temporal information — they encode
recent bolus patterns that drift over time.

Hypothesis: **Mechanistic ratio features** normalize out absolute levels,
capturing biological mechanisms that should generalize across time:

  1. ISF power-law residual  — local dose–response deviation
  2. IOB persistence ratio   — fraction of recent insulin still "active"
  3. Glucose distance from homeostasis — z-scored BG level
  4. Correction density ratio — recent vs historical correction frequency
  5. Bolus efficiency index  — recent vs historical ISF effectiveness

Sub-experiments:
  EXP-2532a  Feature engineering (5 mechanistic ratio features)
  EXP-2532b  Temporal CV: {Ridge, GBM} × {baseline, +ratio features}
  EXP-2532c  Feature stability (fold-to-fold correlation variance)
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
RESULTS_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent
    / 'externals' / 'experiments'
)
DATA_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / 'externals' / 'ns-parquet' / 'training' / 'grid.parquet'
)
EXP2531_PATH = RESULTS_DIR / 'exp-2531_nonlinear_pd.json'

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
HORIZONS = {'h12': 12, 'h30': 30, 'h60': 60}   # 5-min steps
ALPHA = 1.0
N_FOLDS = 5
MIN_ROWS_PER_PATIENT = 500

# Window sizes (5-min steps)
SHORT_WINDOW = 24    # 2 h
LONG_WINDOW = 144    # 12 h
MEDIUM_WINDOW = 48   # 4 h

MIN_CORRECTION_BOLUS = 0.3  # U

BASELINE_FEATURES = ['glucose', 'iob', 'cob', 'net_basal', 'glucose_roc']

RATIO_FEATURES = [
    'isf_powerlaw_residual',
    'iob_persistence_ratio',
    'glucose_homeostasis_dist',
    'correction_density_ratio',
    'bolus_efficiency_index',
]

GBM_PARAMS = {
    'n_estimators': 200,
    'max_depth': 5,
    'learning_rate': 0.1,
    'min_samples_leaf': 20,
}


# ===================================================================
# Data loading
# ===================================================================
def load_grid():
    """Load grid parquet with relevant columns."""
    cols = [
        'patient_id', 'time', 'glucose', 'glucose_roc',
        'iob', 'cob', 'net_basal', 'bolus', 'bolus_smb',
        'time_since_bolus_min', 'scheduled_isf',
    ]
    df = pd.read_parquet(DATA_PATH, columns=cols)
    df = df.sort_values(['patient_id', 'time']).reset_index(drop=True)
    return df


# ===================================================================
# EXP-2532a: Mechanistic ratio feature engineering
# ===================================================================
def engineer_ratio_features(pdf):
    """Compute 5 mechanistic ratio features for one patient (sorted by time).

    All features are designed as RATIOS or z-scores so they normalize out
    absolute levels and should remain stable across temporal folds.
    """
    df = pdf.copy()
    n = len(df)
    bolus = df['bolus'].fillna(0.0).values
    iob = df['iob'].fillna(0.0).values
    glucose = df['glucose'].values
    isf = df['scheduled_isf'].fillna(0.0).values

    # ------------------------------------------------------------------
    # 1. ISF power-law residual
    #    log(observed_drop / (dose × ISF)) — deviation from linear ISF
    #    Use glucose_roc as proxy for observed drop.  For each 5-min step
    #    the expected linear drop is -(bolus × ISF / DIA-minutes).  We use
    #    the ratio: actual_drop / expected_drop.
    #    Clamped and log-transformed for stability.
    # ------------------------------------------------------------------
    glucose_roc = df['glucose_roc'].fillna(0.0).values
    observed_drop = -glucose_roc  # positive when BG is falling

    # Expected drop per 5-min step assuming DIA ≈ 5 h = 300 min
    # and even distribution: expected_drop_per_step = bolus * ISF / 60 steps
    dia_steps = 60.0
    expected_drop = np.where(
        (bolus > 0) & (isf > 0),
        bolus * isf / dia_steps,
        np.nan,
    )

    # Forward-fill expected_drop within a 2h window to capture ongoing effect
    exp_series = pd.Series(expected_drop)
    expected_drop_ff = exp_series.ffill(limit=SHORT_WINDOW).values

    ratio = np.where(
        (expected_drop_ff > 0) & np.isfinite(expected_drop_ff),
        observed_drop / expected_drop_ff,
        0.0,
    )
    # Clamp to [-5, 5] to avoid extreme outliers, then store as-is (no log
    # to avoid NaN on negatives).  Negative = less drop than expected
    # (saturation).
    df['isf_powerlaw_residual'] = np.clip(ratio, -5.0, 5.0)

    # ------------------------------------------------------------------
    # 2. IOB persistence ratio: iob / total_insulin_12h
    #    What fraction of recent insulin is still "active".
    #    Low ratio = most insulin has decayed but persistent effects remain.
    # ------------------------------------------------------------------
    total_insulin_12h = pd.Series(bolus).rolling(
        window=LONG_WINDOW, min_periods=1
    ).sum().values.copy()
    # Add SMB to the total
    smb = df['bolus_smb'].fillna(0.0).values
    total_insulin_12h += pd.Series(smb).rolling(
        window=LONG_WINDOW, min_periods=1
    ).sum().values

    df['iob_persistence_ratio'] = np.where(
        total_insulin_12h > 0.01,
        iob / total_insulin_12h,
        0.0,
    )

    # ------------------------------------------------------------------
    # 3. Glucose distance from homeostasis (z-score)
    #    (sgv - patient_median) / patient_std
    #    Uses expanding window for patient-specific normalization so it
    #    adapts but never looks forward.
    # ------------------------------------------------------------------
    g_series = pd.Series(glucose)
    expanding_median = g_series.expanding(min_periods=50).median().values
    expanding_std = g_series.expanding(min_periods=50).std().values
    # Floor std to avoid division by zero
    expanding_std = np.where(expanding_std > 1.0, expanding_std, 1.0)

    df['glucose_homeostasis_dist'] = np.where(
        np.isfinite(expanding_median) & np.isfinite(expanding_std),
        (glucose - expanding_median) / expanding_std,
        0.0,
    )

    # ------------------------------------------------------------------
    # 4. Correction density ratio: corrections_2h / corrections_12h
    #    Recent vs historical correction frequency.
    #    High = active correction episode; Low = stable period.
    # ------------------------------------------------------------------
    correction_flag = np.where(bolus >= MIN_CORRECTION_BOLUS, 1.0, 0.0)
    corrections_2h = pd.Series(correction_flag).rolling(
        window=SHORT_WINDOW, min_periods=1
    ).sum().values
    corrections_12h = pd.Series(correction_flag).rolling(
        window=LONG_WINDOW, min_periods=1
    ).sum().values

    df['correction_density_ratio'] = np.where(
        corrections_12h > 0,
        corrections_2h / corrections_12h,
        0.0,
    )

    # ------------------------------------------------------------------
    # 5. Bolus efficiency index: recent_bg_drop_per_unit / historical
    #    Ratio of recent to historical ISF effectiveness.
    #    <1 means current corrections are less effective than usual.
    #
    #    We compute a rolling "effective ISF" = cumulative BG change per
    #    cumulative bolus unit, over short vs long windows.
    # ------------------------------------------------------------------
    # BG change per step (use ROC already in mg/dL/5min)
    bg_change = glucose_roc

    # Weighted by bolus presence: only count BG changes near boluses
    bolus_weight = pd.Series(
        np.where(bolus > 0, 1.0, 0.0)
    ).rolling(window=SHORT_WINDOW, min_periods=1).max().values

    weighted_bg_change = bg_change * bolus_weight

    recent_bg_drop = pd.Series(-weighted_bg_change).rolling(
        window=SHORT_WINDOW, min_periods=1
    ).mean().values
    recent_bolus_sum = pd.Series(bolus).rolling(
        window=SHORT_WINDOW, min_periods=1
    ).sum().values
    recent_isf = np.where(
        recent_bolus_sum > 0.01,
        recent_bg_drop / recent_bolus_sum,
        np.nan,
    )

    hist_bg_drop = pd.Series(-weighted_bg_change).rolling(
        window=LONG_WINDOW, min_periods=1
    ).mean().values
    hist_bolus_sum = pd.Series(bolus).rolling(
        window=LONG_WINDOW, min_periods=1
    ).sum().values
    hist_isf = np.where(
        hist_bolus_sum > 0.01,
        hist_bg_drop / hist_bolus_sum,
        np.nan,
    )

    efficiency = np.where(
        np.isfinite(recent_isf) & np.isfinite(hist_isf) & (np.abs(hist_isf) > 1e-6),
        recent_isf / hist_isf,
        1.0,  # default to neutral
    )
    df['bolus_efficiency_index'] = np.clip(efficiency, 0.0, 5.0)

    return df


# ===================================================================
# Helpers
# ===================================================================
def build_targets(df, horizon_steps):
    """Target = glucose shifted forward by horizon_steps within each patient."""
    return df.groupby('patient_id')['glucose'].shift(-horizon_steps)


def _clean_Xy(X, y):
    mask = np.isfinite(X).all(axis=1) & np.isfinite(y)
    return X[mask], y[mask], mask


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
    return GradientBoostingRegressor(
        n_estimators=GBM_PARAMS['n_estimators'],
        max_depth=GBM_PARAMS['max_depth'],
        learning_rate=GBM_PARAMS['learning_rate'],
        min_samples_leaf=GBM_PARAMS['min_samples_leaf'],
    )


def run_temporal_cv(model_factory, X, y, feature_names=None, n_folds=N_FOLDS):
    """TimeSeriesSplit CV (chronological, no shuffling). Returns per-fold R²."""
    X_clean, y_clean, _ = _clean_Xy(X, y)
    if len(X_clean) < n_folds * 50:
        return None

    tscv = TimeSeriesSplit(n_splits=n_folds)
    fold_r2 = []
    y_pred_all = np.full(len(y_clean), np.nan)

    for train_idx, test_idx in tscv.split(X_clean):
        model = model_factory()
        if feature_names is not None:
            X_train = pd.DataFrame(X_clean[train_idx], columns=feature_names)
            X_test = pd.DataFrame(X_clean[test_idx], columns=feature_names)
        else:
            X_train, X_test = X_clean[train_idx], X_clean[test_idx]
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


# ===================================================================
# EXP-2532b: 2×2 temporal CV comparison
# ===================================================================
def run_2x2_comparison(df):
    """Run {Ridge, GBM} × {baseline, +ratio} with temporal CV."""
    patients = sorted(df['patient_id'].unique())
    all_features = BASELINE_FEATURES + RATIO_FEATURES

    configs = {
        'ridge_base':  (make_ridge, BASELINE_FEATURES),
        'ridge_ratio': (make_ridge, all_features),
        'gbm_base':    (make_gbm,   BASELINE_FEATURES),
        'gbm_ratio':   (make_gbm,   all_features),
    }

    results = {h: {cfg: [] for cfg in configs} for h in HORIZONS}
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
                fn = feat_list if USE_LIGHTGBM and 'gbm' in cfg_name else None
                metrics = run_temporal_cv(factory, X, y, feature_names=fn)
                if metrics:
                    metrics['patient'] = str(pid)
                    results[hname][cfg_name].append(metrics)

    return results


# ===================================================================
# EXP-2532c: Feature stability analysis
# ===================================================================
def run_feature_stability(df):
    """For each feature, compute correlation with h60 target in each temporal fold.

    A temporally-robust feature should have SIMILAR correlation across folds
    (low fold-to-fold variance).
    """
    all_features = BASELINE_FEATURES + RATIO_FEATURES
    horizon_steps = HORIZONS['h60']

    patients = sorted(df['patient_id'].unique())
    # Concatenate valid patients
    patient_dfs = []
    for pid in patients:
        pdf = df[df['patient_id'] == pid]
        if len(pdf) >= MIN_ROWS_PER_PATIENT:
            pdf = pdf.copy()
            pdf['target_h60'] = build_targets(pdf, horizon_steps).values
            patient_dfs.append(pdf)

    if not patient_dfs:
        return {}

    combined = pd.concat(patient_dfs, ignore_index=True)
    mask = combined['target_h60'].notna()
    for f in all_features:
        mask &= combined[f].notna() & np.isfinite(combined[f])
    combined = combined[mask].reset_index(drop=True)

    tscv = TimeSeriesSplit(n_splits=N_FOLDS)
    stability = {f: {'fold_corrs': [], 'fold_sizes': []} for f in all_features}

    for fold_idx, (_, test_idx) in enumerate(tscv.split(combined)):
        fold_data = combined.iloc[test_idx]
        target = fold_data['target_h60'].values
        for feat in all_features:
            vals = fold_data[feat].values
            if len(vals) > 30 and np.std(vals) > 1e-8 and np.std(target) > 1e-8:
                corr = float(np.corrcoef(vals, target)[0, 1])
            else:
                corr = 0.0
            stability[feat]['fold_corrs'].append(corr)
            stability[feat]['fold_sizes'].append(int(len(fold_data)))

    # Compute summary stats
    for feat in all_features:
        corrs = stability[feat]['fold_corrs']
        stability[feat]['corr_mean'] = float(np.mean(corrs))
        stability[feat]['corr_std'] = float(np.std(corrs))
        stability[feat]['corr_range'] = float(max(corrs) - min(corrs))
        stability[feat]['is_ratio'] = feat in RATIO_FEATURES

    return stability


# ===================================================================
# Reporting
# ===================================================================
def load_exp2531_baselines():
    """Load EXP-2531 results for comparison."""
    if not EXP2531_PATH.exists():
        return None
    with open(EXP2531_PATH) as f:
        return json.load(f)


def summarize_config(patient_results):
    """Aggregate per-patient results into summary statistics."""
    if not patient_results:
        return {'n': 0, 'r2_mean': float('nan'), 'r2_std': float('nan'),
                'r2_median': float('nan')}
    r2s = [p['r2_cv_mean'] for p in patient_results]
    return {
        'n': len(r2s),
        'r2_mean': float(np.mean(r2s)),
        'r2_std': float(np.std(r2s)),
        'r2_median': float(np.median(r2s)),
    }


def print_comparison_table(results_2x2, exp2531):
    """Print a clear comparison table."""
    print('\n' + '=' * 90)
    print('EXP-2532b: Temporal CV — {Ridge, GBM} × {baseline, +ratio features}')
    print('=' * 90)

    for hname in HORIZONS:
        print(f'\n--- {hname} ({HORIZONS[hname] * 5} min) ---')
        header = f'{"Config":<18} {"N":>4} {"R² mean":>10} {"R² std":>10} {"R² median":>10}'
        print(header)
        print('-' * len(header))

        summaries = {}
        for cfg in ['ridge_base', 'ridge_ratio', 'gbm_base', 'gbm_ratio']:
            s = summarize_config(results_2x2[hname].get(cfg, []))
            summaries[cfg] = s
            print(f'{cfg:<18} {s["n"]:>4} {s["r2_mean"]:>10.4f} '
                  f'{s["r2_std"]:>10.4f} {s["r2_median"]:>10.4f}')

        # Deltas
        if summaries['ridge_base']['n'] > 0 and summaries['ridge_ratio']['n'] > 0:
            delta_ridge = summaries['ridge_ratio']['r2_mean'] - summaries['ridge_base']['r2_mean']
            print(f'  ΔR² Ridge ratio:  {delta_ridge:+.4f}')
        if summaries['gbm_base']['n'] > 0 and summaries['gbm_ratio']['n'] > 0:
            delta_gbm = summaries['gbm_ratio']['r2_mean'] - summaries['gbm_base']['r2_mean']
            print(f'  ΔR² GBM ratio:    {delta_gbm:+.4f}')

        # EXP-2531 comparison
        if exp2531:
            s31 = exp2531.get('results', {}).get('summary_2x2', {}).get(hname, {})
            if s31:
                print(f'\n  EXP-2531 (raw PD) comparison at {hname}:')
                for key in ['ridge_base', 'ridge_pd', 'gbm_base', 'gbm_pd']:
                    if key in s31:
                        r = s31[key]
                        print(f'    {key:<18} R²={r["r2_mean"]:.4f} ±{r["r2_std"]:.4f}')
                # Delta comparison
                if 'ridge_pd' in s31 and 'ridge_base' in s31:
                    d31_ridge = s31['ridge_pd']['r2_mean'] - s31['ridge_base']['r2_mean']
                    d32_ridge = summaries['ridge_ratio']['r2_mean'] - summaries['ridge_base']['r2_mean']
                    print(f'    Ridge ΔR²: EXP-2531={d31_ridge:+.4f}  EXP-2532={d32_ridge:+.4f}  '
                          f'improvement={d32_ridge - d31_ridge:+.4f}')
                if 'gbm_pd' in s31 and 'gbm_base' in s31:
                    d31_gbm = s31['gbm_pd']['r2_mean'] - s31['gbm_base']['r2_mean']
                    d32_gbm = summaries['gbm_ratio']['r2_mean'] - summaries['gbm_base']['r2_mean']
                    print(f'    GBM   ΔR²: EXP-2531={d31_gbm:+.4f}  EXP-2532={d32_gbm:+.4f}  '
                          f'improvement={d32_gbm - d31_gbm:+.4f}')


def print_stability_table(stability):
    """Print feature stability analysis."""
    print('\n' + '=' * 90)
    print('EXP-2532c: Feature Stability (h60 target correlation across temporal folds)')
    print('=' * 90)
    header = (f'{"Feature":<28} {"Type":<8} {"Corr mean":>10} {"Corr std":>10} '
              f'{"Range":>8} {"Stable?":>8}')
    print(header)
    print('-' * len(header))

    sorted_feats = sorted(stability.items(), key=lambda x: x[1]['corr_std'])
    for feat, s in sorted_feats:
        ftype = 'RATIO' if s['is_ratio'] else 'BASE'
        stable = '✓' if s['corr_std'] < 0.05 else '✗'
        print(f'{feat:<28} {ftype:<8} {s["corr_mean"]:>10.4f} '
              f'{s["corr_std"]:>10.4f} {s["corr_range"]:>8.4f} {stable:>8}')

    # Summary comparison
    base_stds = [s['corr_std'] for f, s in stability.items() if not s['is_ratio']]
    ratio_stds = [s['corr_std'] for f, s in stability.items() if s['is_ratio']]
    if base_stds and ratio_stds:
        print(f'\nMean corr-std  BASELINE features: {np.mean(base_stds):.4f}')
        print(f'Mean corr-std  RATIO features:    {np.mean(ratio_stds):.4f}')
        if np.mean(ratio_stds) < np.mean(base_stds):
            print('→ Ratio features are MORE temporally stable (lower fold-to-fold variance)')
        else:
            print('→ Ratio features are NOT more stable — hypothesis partially refuted')


# ===================================================================
# Main
# ===================================================================
def main():
    t0 = time.time()
    print('EXP-2532: Temporal-Robust PD Feature Redesign')
    print(f'GBM engine: {"LightGBM" if USE_LIGHTGBM else "sklearn GBM"}')

    # Load data
    print('\n[1/4] Loading data...')
    df = load_grid()
    print(f'  Loaded {len(df):,} rows, {df["patient_id"].nunique()} patients')

    # Engineer ratio features per patient
    print('\n[2/4] Engineering mechanistic ratio features (EXP-2532a)...')
    patients = sorted(df['patient_id'].unique())
    engineered = []
    for pid in patients:
        pdf = df[df['patient_id'] == pid].copy()
        pdf = engineer_ratio_features(pdf)
        engineered.append(pdf)
    df = pd.concat(engineered, ignore_index=True)

    # Quick feature summary
    print('\n  Feature distributions:')
    for feat in RATIO_FEATURES:
        vals = df[feat].dropna()
        print(f'    {feat:<28} mean={vals.mean():>8.3f}  std={vals.std():>8.3f}  '
              f'min={vals.min():>8.3f}  max={vals.max():>8.3f}')

    # EXP-2532b: 2×2 comparison
    print('\n[3/4] Running 2×2 temporal CV comparison (EXP-2532b)...')
    results_2x2 = run_2x2_comparison(df)

    # Load EXP-2531 for comparison
    exp2531 = load_exp2531_baselines()
    print_comparison_table(results_2x2, exp2531)

    # EXP-2532c: Feature stability
    print('\n[4/4] Running feature stability analysis (EXP-2532c)...')
    stability = run_feature_stability(df)
    print_stability_table(stability)

    # Determine pass/fail
    # Success = positive ΔR² under temporal CV for at least h60
    h60_summaries = {}
    for cfg in ['ridge_base', 'ridge_ratio', 'gbm_base', 'gbm_ratio']:
        h60_summaries[cfg] = summarize_config(results_2x2['h60'].get(cfg, []))

    delta_ridge_h60 = (h60_summaries['ridge_ratio']['r2_mean']
                       - h60_summaries['ridge_base']['r2_mean'])
    delta_gbm_h60 = (h60_summaries['gbm_ratio']['r2_mean']
                     - h60_summaries['gbm_base']['r2_mean'])

    any_positive = delta_ridge_h60 > 0 or delta_gbm_h60 > 0
    status = 'pass' if any_positive else 'fail'

    # Compare to EXP-2531
    improvement_vs_2531 = {}
    if exp2531:
        s31 = exp2531.get('results', {}).get('summary_2x2', {})
        for hname in HORIZONS:
            if hname in s31:
                d31_ridge = s31[hname].get('ridge_pd', {}).get('r2_mean', 0) - s31[hname].get('ridge_base', {}).get('r2_mean', 0)
                d31_gbm = s31[hname].get('gbm_pd', {}).get('r2_mean', 0) - s31[hname].get('gbm_base', {}).get('r2_mean', 0)
                s32 = {c: summarize_config(results_2x2[hname].get(c, [])) for c in ['ridge_base', 'ridge_ratio', 'gbm_base', 'gbm_ratio']}
                d32_ridge = s32['ridge_ratio']['r2_mean'] - s32['ridge_base']['r2_mean']
                d32_gbm = s32['gbm_ratio']['r2_mean'] - s32['gbm_base']['r2_mean']
                improvement_vs_2531[hname] = {
                    'ridge_delta_2531': d31_ridge,
                    'ridge_delta_2532': d32_ridge,
                    'ridge_improvement': d32_ridge - d31_ridge,
                    'gbm_delta_2531': d31_gbm,
                    'gbm_delta_2532': d32_gbm,
                    'gbm_improvement': d32_gbm - d31_gbm,
                }

    elapsed = time.time() - t0

    print(f'\n{"=" * 90}')
    print(f'VERDICT: {status.upper()}')
    print(f'  h60 ΔR² Ridge (ratio):  {delta_ridge_h60:+.4f}')
    print(f'  h60 ΔR² GBM   (ratio):  {delta_gbm_h60:+.4f}')
    if status == 'pass':
        print('  → Ratio features provide POSITIVE ΔR² under temporal CV!')
        print('    (Unlike EXP-2531 raw PD features which degraded R²)')
    else:
        print('  → Ratio features did NOT improve R² under temporal CV.')
        print('    Mechanistic ratio hypothesis not confirmed.')
    print(f'  Elapsed: {elapsed:.1f}s')

    # Build summary_2x2 for JSON output
    summary_2x2 = {}
    for hname in HORIZONS:
        summary_2x2[hname] = {}
        for cfg in ['ridge_base', 'ridge_ratio', 'gbm_base', 'gbm_ratio']:
            summary_2x2[hname][cfg] = summarize_config(
                results_2x2[hname].get(cfg, [])
            )

    # Save results
    output = {
        'experiment': 'EXP-2532',
        'name': 'Temporal-Robust PD Feature Redesign',
        'status': status,
        'hypothesis': (
            'Mechanistic ratio features (ISF residual, IOB persistence ratio, '
            'glucose z-score, correction density ratio, bolus efficiency index) '
            'should be temporally robust because they normalize out absolute levels, '
            'unlike raw PD features which degraded R² under temporal CV in EXP-2531.'
        ),
        'config': {
            'horizons': {h: s * 5 for h, s in HORIZONS.items()},
            'gbm_engine': 'LightGBM' if USE_LIGHTGBM else 'sklearn GBM',
            'gbm_params': GBM_PARAMS,
            'ridge_alpha': ALPHA,
            'n_folds': N_FOLDS,
            'cv_method': 'TimeSeriesSplit (temporal, no shuffling)',
            'windows': {
                'short_hours': SHORT_WINDOW * 5 / 60,
                'medium_hours': MEDIUM_WINDOW * 5 / 60,
                'long_hours': LONG_WINDOW * 5 / 60,
            },
            'min_correction_bolus': MIN_CORRECTION_BOLUS,
            'baseline_features': BASELINE_FEATURES,
            'ratio_features': RATIO_FEATURES,
        },
        'results': {
            'summary_2x2': summary_2x2,
            'h60_deltas': {
                'ridge_ratio_delta': delta_ridge_h60,
                'gbm_ratio_delta': delta_gbm_h60,
            },
            'improvement_vs_2531': improvement_vs_2531,
            'feature_stability': stability,
            'per_patient': {
                hname: {
                    cfg: results_2x2[hname].get(cfg, [])
                    for cfg in ['ridge_base', 'ridge_ratio', 'gbm_base', 'gbm_ratio']
                }
                for hname in HORIZONS
            },
        },
        'elapsed_seconds': round(elapsed, 1),
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / 'exp-2532_temporal_pd.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f'\nResults saved to {out_path}')


if __name__ == '__main__':
    main()
