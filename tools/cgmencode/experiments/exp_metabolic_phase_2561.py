#!/usr/bin/env python3
"""
EXP-2561: Metabolic Phase Mismatch as Hypo Predictor

Hypothesis:
    The mismatch between carb absorption phase and insulin action phase
    predicts hypoglycemia better than glucose trajectory alone. When insulin
    demand exceeds carb supply (negative metabolic phase), the patient is
    at elevated hypo risk even if current glucose is normal.

Background:
    - E-series experiments (EXP-412, 420) found hypo prediction ceiling at
      AUC ~0.69-0.73 regardless of model architecture or feature engineering.
    - The E-series report identified "metabolic phase signal" as the most
      promising untested hypothesis for breaking this ceiling.
    - Current hypo predictors rely on glucose trajectory (81% importance)
      and rate-of-change (11%). IOB-based features consistently fail.
    - The metabolic_engine already decomposes supply (carb absorption) and
      demand (insulin action). The RATIO of these at each timestep defines
      a "metabolic phase" that may predict glucose direction better than
      glucose level or slope alone.

Method:
    - For each 5-min window, compute:
      1. metabolic_phase = supply - demand (net flux direction)
      2. phase_momentum = d(metabolic_phase)/dt (acceleration of imbalance)
      3. phase_integral = cumulative sum of phase over past 30/60/120 min
      4. supply_demand_ratio = supply / (demand + ε)
      5. phase_duration = minutes since last phase sign change
    - Label: hypo event (glucose < 70 mg/dL) within 30/60/120 min
    - Compare:
      A) Glucose-only baseline (trajectory + ROC + acceleration)
      B) + metabolic phase features
      C) Phase features only (no glucose)
    - Evaluate with per-patient temporal CV (last 20% holdout)

Expected outcome:
    If metabolic phase captures causal insulin-carb dynamics that glucose
    trajectory alone misses, we should see AUC improvement beyond 0.73,
    particularly for "surprise" hypos where glucose is still normal but
    the supply-demand balance has shifted.

Sub-experiments:
    EXP-2561a: 30-min hypo prediction (compare to EXP-2539 baseline)
    EXP-2561b: 60-min hypo prediction (harder horizon)
    EXP-2561c: 120-min hypo prediction (strategic planning)
    EXP-2561d: "Surprise" hypo subset (glucose > 120 but hypo within 60 min)
    EXP-2561e: Per-phenotype analysis (Well-Controlled vs Hypo-Prone)
"""

import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / 'externals' / 'experiments'
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class SubExperimentResult:
    """Result of a single sub-experiment."""
    exp_id: str
    horizon_minutes: int
    n_patients: int
    n_windows: int
    n_hypo_events: int
    hypo_rate: float
    # AUC scores per model
    auc_glucose_only: float
    auc_glucose_plus_phase: float
    auc_phase_only: float
    # Per-patient AUC breakdown
    per_patient_auc: Dict[str, Dict[str, float]]
    # Feature importance
    top_features: List[Tuple[str, float]]
    # Delta
    auc_delta: float  # glucose+phase - glucose_only
    conclusion: str


@dataclass
class ExperimentReport:
    """Full EXP-2561 report."""
    exp_id: str = 'EXP-2561'
    hypothesis: str = 'Metabolic phase mismatch predicts hypo beyond glucose trajectory'
    timestamp: str = ''
    runtime_seconds: float = 0.0
    sub_experiments: List[SubExperimentResult] = field(default_factory=list)
    overall_conclusion: str = ''
    next_steps: List[str] = field(default_factory=list)


# ── Feature Engineering ──────────────────────────────────────────────

def compute_metabolic_phase_features(glucose, iob, cob, net_basal,
                                     bolus, carbs, hours,
                                     scheduled_isf, scheduled_cr):
    """Compute metabolic phase features from raw patient data.

    Returns dict of arrays, each of length n.
    """
    n = len(glucose)
    eps = 1e-6

    # Supply: carb absorption proxy (COB decay rate → glucose input)
    # When COB is decreasing, carbs are being absorbed → supply
    cob_diff = np.diff(cob, prepend=cob[0])
    supply = np.clip(-cob_diff, 0, None)  # positive = carbs absorbing

    # Demand: insulin action proxy (IOB decay rate → glucose removal)
    iob_diff = np.diff(iob, prepend=iob[0])
    demand = np.clip(-iob_diff, 0, None)  # positive = insulin acting

    # Scale demand by ISF to get mg/dL equivalent
    isf_safe = np.where(scheduled_isf > 0, scheduled_isf, 50.0)
    demand_mgdl = demand * isf_safe

    # Scale supply by CR/ISF to get mg/dL equivalent
    cr_safe = np.where(scheduled_cr > 0, scheduled_cr, 10.0)
    supply_mgdl = supply * isf_safe / cr_safe

    # Core phase features
    phase = supply_mgdl - demand_mgdl  # positive = net glucose rising
    phase_ratio = supply_mgdl / (demand_mgdl + eps)

    # Phase momentum (derivative)
    phase_momentum = np.diff(phase, prepend=phase[0])

    # Cumulative phase integrals (30, 60, 120 min windows = 6, 12, 24 steps)
    phase_integral_30 = _rolling_sum(phase, 6)
    phase_integral_60 = _rolling_sum(phase, 12)
    phase_integral_120 = _rolling_sum(phase, 24)

    # Phase duration: minutes since last sign change
    phase_duration = _compute_phase_duration(phase)

    # IOB-to-COB ratio (raw, not scaled)
    iob_cob_ratio = iob / (cob + eps)

    # Net basal excess (actual - scheduled would be ideal, use net_basal)
    basal_excess = net_basal  # already net of scheduled

    return {
        'phase': phase,
        'phase_ratio': phase_ratio,
        'phase_momentum': phase_momentum,
        'phase_integral_30': phase_integral_30,
        'phase_integral_60': phase_integral_60,
        'phase_integral_120': phase_integral_120,
        'phase_duration': phase_duration,
        'iob_cob_ratio': iob_cob_ratio,
        'supply_mgdl': supply_mgdl,
        'demand_mgdl': demand_mgdl,
        'basal_excess': basal_excess,
    }


def _rolling_sum(arr, window):
    """Causal rolling sum (only past values)."""
    result = np.zeros_like(arr)
    cumsum = np.cumsum(arr)
    result[window:] = cumsum[window:] - cumsum[:-window]
    result[:window] = cumsum[:window]
    return result


def _compute_phase_duration(phase):
    """Minutes since last phase sign change."""
    n = len(phase)
    duration = np.zeros(n)
    sign = np.sign(phase)
    count = 0
    for i in range(n):
        if i == 0 or sign[i] == sign[i - 1] or sign[i] == 0:
            count += 1
        else:
            count = 1
        duration[i] = count * 5  # 5-min steps
    return duration


# ── Glucose-only baseline features ──────────────────────────────────

def compute_glucose_baseline_features(glucose, hours):
    """Glucose trajectory features matching EXP-2539 baseline."""
    n = len(glucose)

    roc = np.diff(glucose, prepend=glucose[0])  # rate of change
    accel = np.diff(roc, prepend=roc[0])  # acceleration

    # Rolling stats
    mean_30 = _rolling_mean(glucose, 6)
    std_30 = _rolling_std(glucose, 6)
    mean_60 = _rolling_mean(glucose, 12)
    min_30 = _rolling_min(glucose, 6)

    # Distance to hypo threshold
    dist_to_70 = glucose - 70.0

    # Extrapolation: where will glucose be in 30 min at current rate?
    projected_30 = glucose + roc * 6

    return {
        'glucose': glucose,
        'glucose_roc': roc,
        'glucose_accel': accel,
        'glucose_mean_30': mean_30,
        'glucose_std_30': std_30,
        'glucose_mean_60': mean_60,
        'glucose_min_30': min_30,
        'dist_to_70': dist_to_70,
        'projected_30': projected_30,
        'hour_sin': np.sin(2 * np.pi * hours / 24),
        'hour_cos': np.cos(2 * np.pi * hours / 24),
    }


def _rolling_mean(arr, window):
    result = np.zeros_like(arr)
    cumsum = np.cumsum(arr)
    result[window:] = (cumsum[window:] - cumsum[:-window]) / window
    result[:window] = cumsum[:window] / np.arange(1, window + 1)
    return result


def _rolling_std(arr, window):
    mean = _rolling_mean(arr, window)
    sq_mean = _rolling_mean(arr ** 2, window)
    var = np.clip(sq_mean - mean ** 2, 0, None)
    return np.sqrt(var)


def _rolling_min(arr, window):
    from numpy.lib.stride_tricks import sliding_window_view
    n = len(arr)
    result = np.zeros(n)
    if n >= window:
        sw = sliding_window_view(arr, window)
        result[window - 1:] = sw.min(axis=1)
        for i in range(min(window - 1, n)):
            result[i] = arr[:i + 1].min()
    else:
        for i in range(n):
            result[i] = arr[:i + 1].min()
    return result


# ── Labeling ─────────────────────────────────────────────────────────

def label_hypo_events(glucose, horizon_steps):
    """Label each timestep: will hypo occur within horizon_steps?

    Returns binary array: 1 if glucose < 70 at any point in [t+1, t+horizon].
    """
    n = len(glucose)
    labels = np.zeros(n, dtype=np.int32)
    hypo_mask = glucose < 70.0

    # Reverse scan for efficiency
    for i in range(n - 1, -1, -1):
        end = min(i + horizon_steps + 1, n)
        if np.any(hypo_mask[i + 1:end]):
            labels[i] = 1
    return labels


# ── Model Training & Evaluation ──────────────────────────────────────

def train_and_evaluate(X, y, patient_ids, model_name='lgbm'):
    """Train with per-patient temporal split, return mean AUC + per-patient."""
    try:
        from sklearn.metrics import roc_auc_score
        from sklearn.linear_model import LogisticRegression
    except ImportError:
        return 0.5, {}

    unique_pids = sorted(set(patient_ids))
    per_patient = {}
    all_y_true = []
    all_y_prob = []

    for pid in unique_pids:
        mask = np.array([p == pid for p in patient_ids])
        X_p = X[mask]
        y_p = y[mask]

        if len(X_p) < 100 or y_p.sum() < 5 or (1 - y_p).sum() < 5:
            continue

        # Temporal split: train on first 80%, test on last 20%
        cut = int(len(X_p) * 0.8)
        X_train, X_test = X_p[:cut], X_p[cut:]
        y_train, y_test = y_p[:cut], y_p[cut:]

        if y_train.sum() < 3 or y_test.sum() < 2:
            continue

        if model_name == 'logistic':
            model = LogisticRegression(max_iter=1000, C=0.1,
                                       class_weight='balanced')
            # NaN handling
            X_train_clean = np.nan_to_num(X_train, nan=0.0)
            X_test_clean = np.nan_to_num(X_test, nan=0.0)
            model.fit(X_train_clean, y_train)
            y_prob = model.predict_proba(X_test_clean)[:, 1]
        else:
            try:
                import lightgbm as lgb
                model = lgb.LGBMClassifier(
                    n_estimators=200, max_depth=6, learning_rate=0.05,
                    subsample=0.8, colsample_bytree=0.8,
                    scale_pos_weight=max(1, (1 - y_train.mean()) / max(y_train.mean(), 1e-6)),
                    verbose=-1, n_jobs=1,
                )
                model.fit(X_train, y_train)
                y_prob = model.predict_proba(X_test)[:, 1]
            except ImportError:
                # Fallback to logistic regression
                model = LogisticRegression(max_iter=1000, C=0.1,
                                           class_weight='balanced')
                X_train_clean = np.nan_to_num(X_train, nan=0.0)
                X_test_clean = np.nan_to_num(X_test, nan=0.0)
                model.fit(X_train_clean, y_train)
                y_prob = model.predict_proba(X_test_clean)[:, 1]

        try:
            auc = roc_auc_score(y_test, y_prob)
            per_patient[pid] = auc
            all_y_true.extend(y_test.tolist())
            all_y_prob.extend(y_prob.tolist())
        except ValueError:
            continue

    if len(all_y_true) > 0:
        try:
            overall_auc = roc_auc_score(all_y_true, all_y_prob)
        except ValueError:
            overall_auc = np.mean(list(per_patient.values())) if per_patient else 0.5
    else:
        overall_auc = 0.5

    return overall_auc, per_patient


def get_feature_importance(X, y, feature_names):
    """Get feature importance from a quick LightGBM fit."""
    try:
        import lightgbm as lgb
        model = lgb.LGBMClassifier(n_estimators=100, max_depth=4, verbose=-1, n_jobs=1)
        X_clean = np.nan_to_num(X, nan=0.0)
        model.fit(X_clean, y)
        imp = model.feature_importances_
        pairs = sorted(zip(feature_names, imp), key=lambda x: -x[1])
        total = sum(imp)
        return [(name, float(val / total)) for name, val in pairs[:15]]
    except ImportError:
        return []


# ── Main Experiment ──────────────────────────────────────────────────

def load_patient_data():
    """Load 19-patient parquet grid."""
    import pandas as pd
    grid_path = Path(__file__).resolve().parent.parent.parent.parent / \
        'externals' / 'ns-parquet' / 'training' / 'grid.parquet'
    if not grid_path.exists():
        print(f'ERROR: Training grid not found at {grid_path}')
        sys.exit(1)
    return pd.read_parquet(grid_path)


def run_sub_experiment(df, horizon_minutes, exp_id, surprise_only=False,
                       phenotype_filter=None):
    """Run a single sub-experiment at a given horizon."""
    horizon_steps = horizon_minutes // 5
    patients = sorted(df['patient_id'].unique())

    if phenotype_filter:
        patients = [p for p in patients if p in phenotype_filter]

    all_X_glucose = []
    all_X_phase = []
    all_X_combined = []
    all_y = []
    all_pids = []
    glucose_feature_names = None
    phase_feature_names = None
    combined_feature_names = None

    for pid in patients:
        pdf = df[df['patient_id'] == pid].sort_values('time').reset_index(drop=True)

        glucose = pdf['glucose'].values.astype(np.float64)
        iob = pdf['iob'].values.astype(np.float64)
        cob = pdf['cob'].values.astype(np.float64)
        net_basal = pdf['net_basal'].values.astype(np.float64)
        bolus = pdf['bolus'].values.astype(np.float64)
        carbs_col = pdf['carbs'].values.astype(np.float64)
        scheduled_isf = pdf['scheduled_isf'].values.astype(np.float64)
        scheduled_cr = pdf['scheduled_cr'].values.astype(np.float64)

        # Extract hours from time
        hours = pdf['time'].dt.hour.values + pdf['time'].dt.minute.values / 60.0

        # Skip rows with NaN glucose
        valid = ~np.isnan(glucose)
        if valid.sum() < 500:
            continue

        # Forward-fill glucose NaNs for feature computation
        glucose_filled = glucose.copy()
        mask = np.isnan(glucose_filled)
        if mask.any():
            idx = np.where(~mask, np.arange(len(glucose_filled)), 0)
            np.maximum.accumulate(idx, out=idx)
            glucose_filled = glucose_filled[idx]

        # Compute features
        gf = compute_glucose_baseline_features(glucose_filled, hours)
        pf = compute_metabolic_phase_features(
            glucose_filled, iob, cob, net_basal, bolus, carbs_col,
            hours, scheduled_isf, scheduled_cr
        )

        # Label
        labels = label_hypo_events(glucose_filled, horizon_steps)

        # Build feature matrices
        if glucose_feature_names is None:
            glucose_feature_names = list(gf.keys())
            phase_feature_names = list(pf.keys())
            combined_feature_names = glucose_feature_names + phase_feature_names

        X_g = np.column_stack([gf[k] for k in glucose_feature_names])
        X_p = np.column_stack([pf[k] for k in phase_feature_names])
        X_c = np.column_stack([X_g, X_p])

        # Filter valid windows (not in last horizon, valid glucose)
        valid_mask = valid & (np.arange(len(glucose)) < len(glucose) - horizon_steps)

        if surprise_only:
            # Only windows where current glucose > 120 mg/dL
            valid_mask = valid_mask & (glucose_filled > 120.0)

        X_g_valid = X_g[valid_mask]
        X_p_valid = X_p[valid_mask]
        X_c_valid = X_c[valid_mask]
        y_valid = labels[valid_mask]

        all_X_glucose.append(X_g_valid)
        all_X_phase.append(X_p_valid)
        all_X_combined.append(X_c_valid)
        all_y.append(y_valid)
        all_pids.extend([pid] * len(y_valid))

    if not all_X_glucose:
        return None

    X_glucose = np.vstack(all_X_glucose)
    X_phase = np.vstack(all_X_phase)
    X_combined = np.vstack(all_X_combined)
    y = np.concatenate(all_y)
    pids = np.array(all_pids)

    n_hypo = int(y.sum())
    hypo_rate = n_hypo / len(y) if len(y) > 0 else 0

    print(f'\n  {exp_id}: {len(y):,} windows, {n_hypo:,} hypo events ({hypo_rate:.1%})')
    print(f'    {len(set(all_pids))} patients')

    # A) Glucose-only baseline
    print(f'    Training glucose-only model...')
    auc_glucose, pp_glucose = train_and_evaluate(X_glucose, y, pids)
    print(f'    Glucose-only AUC: {auc_glucose:.3f}')

    # B) Glucose + phase
    print(f'    Training glucose+phase model...')
    auc_combined, pp_combined = train_and_evaluate(X_combined, y, pids)
    print(f'    Glucose+phase AUC: {auc_combined:.3f}')

    # C) Phase only
    print(f'    Training phase-only model...')
    auc_phase, pp_phase = train_and_evaluate(X_phase, y, pids)
    print(f'    Phase-only AUC: {auc_phase:.3f}')

    # Feature importance from combined model
    top_features = get_feature_importance(X_combined, y, combined_feature_names)

    delta = auc_combined - auc_glucose
    if delta > 0.02:
        conclusion = f'POSITIVE: +{delta:.3f} AUC from metabolic phase features'
    elif delta > 0.005:
        conclusion = f'MARGINAL: +{delta:.3f} AUC (small but consistent improvement)'
    elif delta > -0.005:
        conclusion = f'NEUTRAL: {delta:+.3f} AUC (no meaningful difference)'
    else:
        conclusion = f'NEGATIVE: {delta:+.3f} AUC (phase features hurt)'

    # Per-patient detail
    per_patient_auc = {}
    for pid in sorted(set(all_pids)):
        per_patient_auc[pid] = {
            'glucose_only': pp_glucose.get(pid, float('nan')),
            'glucose_plus_phase': pp_combined.get(pid, float('nan')),
            'phase_only': pp_phase.get(pid, float('nan')),
        }

    return SubExperimentResult(
        exp_id=exp_id,
        horizon_minutes=horizon_minutes,
        n_patients=len(set(all_pids)),
        n_windows=len(y),
        n_hypo_events=n_hypo,
        hypo_rate=hypo_rate,
        auc_glucose_only=auc_glucose,
        auc_glucose_plus_phase=auc_combined,
        auc_phase_only=auc_phase,
        per_patient_auc=per_patient_auc,
        top_features=top_features,
        auc_delta=delta,
        conclusion=conclusion,
    )


def classify_phenotypes(df):
    """Split patients into Well-Controlled and Hypo-Prone (EXP-2541)."""
    well_controlled = []
    hypo_prone = []

    for pid in df['patient_id'].unique():
        pdf = df[df['patient_id'] == pid]
        glucose = pdf['glucose'].dropna().values
        if len(glucose) < 288:
            continue

        tir = np.mean((glucose >= 70) & (glucose <= 180))
        tbr = np.mean(glucose < 70)
        cv = np.std(glucose) / np.mean(glucose)

        if tbr > 0.04 or cv > 0.40:
            hypo_prone.append(pid)
        else:
            well_controlled.append(pid)

    return well_controlled, hypo_prone


def main():
    t0 = time.time()
    print('=' * 70)
    print('EXP-2561: Metabolic Phase Mismatch as Hypo Predictor')
    print('=' * 70)

    df = load_patient_data()
    print(f'Loaded {len(df):,} rows, {df["patient_id"].nunique()} patients')

    report = ExperimentReport(
        timestamp=time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
    )

    # Sub-experiment a: 30-min hypo prediction
    result_a = run_sub_experiment(df, 30, 'EXP-2561a')
    if result_a:
        report.sub_experiments.append(result_a)

    # Sub-experiment b: 60-min hypo prediction
    result_b = run_sub_experiment(df, 60, 'EXP-2561b')
    if result_b:
        report.sub_experiments.append(result_b)

    # Sub-experiment c: 120-min hypo prediction
    result_c = run_sub_experiment(df, 120, 'EXP-2561c')
    if result_c:
        report.sub_experiments.append(result_c)

    # Sub-experiment d: "Surprise" hypos (glucose > 120, hypo within 60 min)
    result_d = run_sub_experiment(df, 60, 'EXP-2561d', surprise_only=True)
    if result_d:
        report.sub_experiments.append(result_d)

    # Sub-experiment e: Per-phenotype analysis
    well_controlled, hypo_prone = classify_phenotypes(df)
    print(f'\nPhenotypes: {len(well_controlled)} Well-Controlled, {len(hypo_prone)} Hypo-Prone')

    result_e_wc = run_sub_experiment(df, 60, 'EXP-2561e-WC',
                                     phenotype_filter=well_controlled)
    result_e_hp = run_sub_experiment(df, 60, 'EXP-2561e-HP',
                                     phenotype_filter=hypo_prone)
    if result_e_wc:
        report.sub_experiments.append(result_e_wc)
    if result_e_hp:
        report.sub_experiments.append(result_e_hp)

    # Overall conclusion
    deltas = [r.auc_delta for r in report.sub_experiments]
    mean_delta = np.mean(deltas) if deltas else 0

    if mean_delta > 0.02:
        report.overall_conclusion = (
            f'HYPOTHESIS SUPPORTED: Metabolic phase features improve hypo prediction '
            f'by {mean_delta:+.3f} AUC on average. Recommend productionizing phase '
            f'features into hypo_predictor.py.'
        )
        report.next_steps = [
            'Add metabolic phase features to production hypo_predictor.py',
            'Test with E-series CNN architecture (EXP-420 extension)',
            'Evaluate surprise-hypo alert feasibility',
        ]
    elif mean_delta > 0.005:
        report.overall_conclusion = (
            f'MARGINAL SUPPORT: Phase features add {mean_delta:+.3f} AUC on average. '
            f'May be useful for specific phenotypes or horizons.'
        )
        report.next_steps = [
            'Test interaction features (phase × glucose_roc)',
            'Evaluate if benefit is phenotype-specific',
            'Try phase features with XGBoost instead of LightGBM',
        ]
    else:
        report.overall_conclusion = (
            f'HYPOTHESIS NOT SUPPORTED: Phase features add {mean_delta:+.3f} AUC. '
            f'The hypo ceiling is not a feature problem — it is information-theoretic. '
            f'Consider external data (activity, stress) or different framing.'
        )
        report.next_steps = [
            'Explore activity/accelerometer data integration',
            'Test meal announcement timing as predictor',
            'Accept hypo ceiling and focus on settings optimization instead',
        ]

    report.runtime_seconds = time.time() - t0

    # Print summary
    print('\n' + '=' * 70)
    print('RESULTS SUMMARY')
    print('=' * 70)
    for r in report.sub_experiments:
        print(f'\n  {r.exp_id} ({r.horizon_minutes}min):')
        print(f'    Glucose-only: {r.auc_glucose_only:.3f}')
        print(f'    + Phase:      {r.auc_glucose_plus_phase:.3f} ({r.auc_delta:+.3f})')
        print(f'    Phase-only:   {r.auc_phase_only:.3f}')
        print(f'    → {r.conclusion}')
        if r.top_features:
            print(f'    Top features: {", ".join(f"{n}({v:.2f})" for n, v in r.top_features[:5])}')

    print(f'\n  OVERALL: {report.overall_conclusion}')
    print(f'  Runtime: {report.runtime_seconds:.0f}s')

    # Save results
    result_path = RESULTS_DIR / 'exp-2561_metabolic_phase_hypo.json'
    with open(result_path, 'w') as f:
        json.dump(asdict(report), f, indent=2, default=str)
    print(f'\n  Results saved to {result_path}')

    return report


if __name__ == '__main__':
    main()
