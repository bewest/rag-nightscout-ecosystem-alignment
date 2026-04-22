#!/usr/bin/env python3
"""
EXP-2830: Formulation-Constant Hypothesis Test
================================================

Hypothesis (user-proposed):
  Insulin lowering effect is largely a property of the FORMULATION
  (action envelope, ~72 mg/dL/U baseline lowering). Inter-patient
  variation in observed ISF is dominated by EGP variation, not by
  intrinsic insulin sensitivity differences.

Math:
  observed_drop = K_formulation × dose - EGP × t_hours - other_losses
  ISF_obs = drop/dose ≈ K_formulation - (EGP × t_hours) / dose

Therefore:
  - If K is constant: drop at peak insulin action ≈ K × dose for all patients
  - Variance in observed ISF should track variance in (EGP × t / dose)
  - Mean ISF across patients should equal K minus mean (EGP × t / dose)

Method:
  1. Extract correction events with rigorous timing
  2. Measure drop AT PEAK INSULIN ACTION (~75 min for rapid analog)
     vs measure drop OVER FULL WINDOW (3h)
  3. Compare per-patient distributions
  4. Test whether peak-time ISF is more uniform across patients than
     full-window ISF
  5. Regress full-window ISF residual against EGP estimate
  6. Estimate K_formulation as the population intercept when EGP=0

Multi-layer stratification:
  Layer 1: Per-patient mean ISF
  Layer 2: Subtract EGP × t / dose (formulation isolation)
  Layer 3: Per-patient residual after K + EGP

Success criteria:
  P1: Peak-time drop/dose has narrower CV than full-window drop/dose
      (formulation effect more uniform at peak)
  P2: Mean drop/dose at peak is in plausible formulation range (50-100 mg/dL/U)
  P3: After K + EGP correction, residual variance reduces by >30%
  P4: Regression: ISF_residual vs (EGP × t / dose) yields coefficient
      between -0.5 and -2.0 (theoretically -1 if hypothesis exact)
  P5: K_formulation estimate (intercept) within 50-100 mg/dL/U
"""

import json
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats as sp_stats
from sklearn.linear_model import LinearRegression

warnings.filterwarnings('ignore')

EXP_ID = 2830
TITLE = "Formulation-Constant Hypothesis Test"
EXCLUDE = {'odc-84181797', 'h', 'j'}

# Reference: insulin lispro/aspart peak ≈ 75 min, DIA ~ 5-6h
PEAK_INSULIN_MIN = 75
PEAK_INSULIN_ROW = PEAK_INSULIN_MIN // 5  # 15 rows
FULL_WINDOW_HOURS = 3
FULL_WINDOW_ROW = FULL_WINDOW_HOURS * 12  # 36 rows
USER_HYPOTHESIZED_K = 72  # mg/dL/U from action envelope

print(f"[EXP-{EXP_ID}] {TITLE}")
print("=" * 70)

# ── Data loading ─────────────────────────────────────────────────────────
grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
grid = grid[~grid['patient_id'].isin(EXCLUDE)].copy()
grid = grid.sort_values(['patient_id', 'time']).reset_index(drop=True)
canonical_egp = pd.read_parquet("externals/experiments/exp-2820_canonical_egp.parquet")
egp_lookup = dict(zip(canonical_egp['patient_id'], canonical_egp['canonical_egp_mg_dL_hr']))

print(f"Patients: {grid['patient_id'].nunique()}")
print(f"With canonical EGP: {sum(pd.notna(v) for v in egp_lookup.values())}")
print(f"User-hypothesized K_formulation: {USER_HYPOTHESIZED_K} mg/dL/U")
print(f"Peak insulin time: {PEAK_INSULIN_MIN} min ({PEAK_INSULIN_ROW} rows)")
print(f"Full window: {FULL_WINDOW_HOURS}h ({FULL_WINDOW_ROW} rows)")

# ── Extract events with BOTH peak-time and full-window measurements ──────
def extract_correction_events(pdata):
    """Pure correction events: high BG, bolus, no carbs ±3h.
    Returns events with drop_at_peak (75min) and drop_full (3h).
    """
    pdata = pdata.sort_values('time').reset_index(drop=True)
    bg = pdata['glucose'].values
    bolus = pdata['bolus'].fillna(0).values
    carbs = pdata['carbs'].fillna(0).values
    iob = pdata['iob'].fillna(0).values
    n = len(pdata)
    events = []
    for i in range(72, n - FULL_WINDOW_ROW - 6):
        if bolus[i] < 0.5 or bg[i] < 180:
            continue
        if carbs[max(0, i - 36):min(n, i + 36)].sum() > 5:
            continue
        # Low IOB at start (clean correction)
        if iob[i] > 2.0:
            continue
        # Time-in-high backward 1-6h
        back_bg = bg[max(0, i - 72):i]
        if np.isnan(back_bg).any():
            continue
        time_in_high = (back_bg > 180).sum() / 12.0
        if not (1 <= time_in_high <= 6):
            continue
        # Forward window
        fwd_bg = bg[i:i + FULL_WINDOW_ROW + 6]
        if np.isnan(fwd_bg).any():
            continue
        # Drop at peak (around row 15 from start, with ±2 row slop)
        peak_window = fwd_bg[max(0, PEAK_INSULIN_ROW - 2):PEAK_INSULIN_ROW + 3]
        drop_peak = bg[i] - np.min(peak_window)
        # Drop full window (find nadir within 3h)
        drop_full = bg[i] - np.min(fwd_bg)
        if drop_peak <= 0 and drop_full <= 0:
            continue
        events.append({
            'bg_start': float(bg[i]),
            'dose': float(bolus[i]),
            'drop_peak': float(drop_peak),
            'drop_full': float(drop_full),
            'time_in_high_h': float(time_in_high),
            'isf_peak': float(drop_peak / bolus[i]),
            'isf_full': float(drop_full / bolus[i]),
            't_hours_full': float(FULL_WINDOW_HOURS),
        })
    return events

print("\n── Extracting events ──")
all_events = []
for pid in sorted(grid['patient_id'].unique()):
    pdata = grid[grid['patient_id'] == pid]
    events = extract_correction_events(pdata)
    for e in events:
        e['patient_id'] = pid
        e['egp_mg_dL_hr'] = egp_lookup.get(pid, np.nan)
        all_events.append(e)

events_df = pd.DataFrame(all_events)
print(f"  {len(events_df)} correction events from {events_df['patient_id'].nunique()} patients")

# ── Per-patient summaries ─────────────────────────────────────────────────
patient_stats = events_df.groupby('patient_id').agg(
    n=('isf_peak', 'count'),
    isf_peak_med=('isf_peak', 'median'),
    isf_full_med=('isf_full', 'median'),
    isf_peak_cv=('isf_peak', lambda x: np.std(x) / np.mean(x) if np.mean(x) > 0 else np.nan),
    isf_full_cv=('isf_full', lambda x: np.std(x) / np.mean(x) if np.mean(x) > 0 else np.nan),
    egp=('egp_mg_dL_hr', 'first'),
).query('n >= 5').reset_index()

print(f"\n  {len(patient_stats)} patients with ≥5 events")

# ── Population statistics: peak vs full ──────────────────────────────────
print("\n── Peak-time vs Full-window comparison ──")
print(f"{'metric':<25} {'PEAK (75min)':>15} {'FULL (3h)':>15}")
print(f"{'population mean ISF':<25} {patient_stats['isf_peak_med'].mean():>15.1f} {patient_stats['isf_full_med'].mean():>15.1f}")
print(f"{'population median ISF':<25} {patient_stats['isf_peak_med'].median():>15.1f} {patient_stats['isf_full_med'].median():>15.1f}")
print(f"{'inter-patient CV':<25} "
      f"{patient_stats['isf_peak_med'].std() / patient_stats['isf_peak_med'].mean():>15.3f} "
      f"{patient_stats['isf_full_med'].std() / patient_stats['isf_full_med'].mean():>15.3f}")
print(f"{'inter-patient std':<25} "
      f"{patient_stats['isf_peak_med'].std():>15.1f} "
      f"{patient_stats['isf_full_med'].std():>15.1f}")
print(f"{'inter-patient range':<25} "
      f"{patient_stats['isf_peak_med'].max() - patient_stats['isf_peak_med'].min():>15.1f} "
      f"{patient_stats['isf_full_med'].max() - patient_stats['isf_full_med'].min():>15.1f}")
print(f"{'min':<25} {patient_stats['isf_peak_med'].min():>15.1f} {patient_stats['isf_full_med'].min():>15.1f}")
print(f"{'max':<25} {patient_stats['isf_peak_med'].max():>15.1f} {patient_stats['isf_full_med'].max():>15.1f}")
print(f"{'median intra-patient CV':<25} {patient_stats['isf_peak_cv'].median():>15.3f} {patient_stats['isf_full_cv'].median():>15.3f}")

peak_cv_inter = patient_stats['isf_peak_med'].std() / patient_stats['isf_peak_med'].mean()
full_cv_inter = patient_stats['isf_full_med'].std() / patient_stats['isf_full_med'].mean()
peak_more_uniform = peak_cv_inter < full_cv_inter

# ── Compare to user hypothesis ───────────────────────────────────────────
peak_pop_mean = patient_stats['isf_peak_med'].mean()
print(f"\n── User hypothesis: K_formulation ≈ {USER_HYPOTHESIZED_K} mg/dL/U ──")
print(f"  Observed peak-time ISF (population mean): {peak_pop_mean:.1f} mg/dL/U")
print(f"  Difference from hypothesized K: {peak_pop_mean - USER_HYPOTHESIZED_K:+.1f}")
print(f"  Within ±20% of K=72: {abs(peak_pop_mean - USER_HYPOTHESIZED_K) / USER_HYPOTHESIZED_K * 100:.1f}%")

# ── EGP × t / dose regression ────────────────────────────────────────────
print("\n── Multi-layer ISF decomposition ──")
events_with_egp = events_df.dropna(subset=['egp_mg_dL_hr']).copy()
events_with_egp['egp_burden'] = events_with_egp['egp_mg_dL_hr'] * events_with_egp['t_hours_full'] / events_with_egp['dose']
print(f"  Events with EGP: {len(events_with_egp)}")
print(f"  EGP burden = (EGP × t) / dose")
print(f"    range: [{events_with_egp['egp_burden'].min():.1f}, {events_with_egp['egp_burden'].max():.1f}] mg/dL/U")
print(f"    median: {events_with_egp['egp_burden'].median():.1f}")

# Regression: ISF_full ~ EGP_burden
if len(events_with_egp) >= 30:
    X = events_with_egp[['egp_burden']].values
    y = events_with_egp['isf_full'].values
    reg = LinearRegression().fit(X, y)
    intercept = float(reg.intercept_)
    slope = float(reg.coef_[0])
    pred = reg.predict(X)
    residuals = y - pred
    var_orig = np.var(y)
    var_resid = np.var(residuals)
    var_explained_pct = (1 - var_resid / var_orig) * 100

    print(f"\n  Regression: ISF_full = K + β × (EGP × t / dose)")
    print(f"    Intercept (K_estimate): {intercept:.2f} mg/dL/U")
    print(f"    Slope β: {slope:.3f} (theoretical: -1.0 if hypothesis exact)")
    print(f"    Variance explained: {var_explained_pct:.1f}%")
    print(f"    Original variance: {var_orig:.1f}")
    print(f"    Residual variance: {var_resid:.1f}")
else:
    intercept, slope, var_explained_pct = np.nan, np.nan, 0

# ── Per-patient: does EGP explain inter-patient ISF variance? ───────────
print("\n── Per-patient: EGP vs ISF correlation ──")
ps_egp = patient_stats.dropna(subset=['egp'])
if len(ps_egp) >= 5:
    rho_peak, p_peak = sp_stats.spearmanr(ps_egp['egp'], ps_egp['isf_peak_med'])
    rho_full, p_full = sp_stats.spearmanr(ps_egp['egp'], ps_egp['isf_full_med'])
    print(f"  EGP vs ISF_peak: ρ={rho_peak:+.3f} (p={p_peak:.3f}), n={len(ps_egp)}")
    print(f"  EGP vs ISF_full: ρ={rho_full:+.3f} (p={p_full:.3f}), n={len(ps_egp)}")
    # Hypothesis: higher EGP → lower observed ISF (more headwind to overcome)
    print(f"  Theory predicts NEGATIVE correlation (higher EGP, lower observed drop/dose)")

# ── Stratified extraction: K vs EGP signal layers ───────────────────────
print("\n── Multi-layer signal decomposition ──")
print(f"  Layer 1 (raw ISF_full per patient):    inter-patient CV = {full_cv_inter:.3f}")
print(f"  Layer 2 (peak-time ISF per patient):   inter-patient CV = {peak_cv_inter:.3f}")
if not pd.isna(intercept):
    # Apply correction: corrected ISF = ISF_full + slope × EGP_burden (remove EGP component)
    events_with_egp['isf_corrected'] = events_with_egp['isf_full'] - slope * events_with_egp['egp_burden']
    patient_corrected = events_with_egp.groupby('patient_id')['isf_corrected'].median()
    corrected_cv = patient_corrected.std() / patient_corrected.mean()
    print(f"  Layer 3 (EGP-burden corrected ISF):    inter-patient CV = {corrected_cv:.3f}")
    cv_reduction = (full_cv_inter - corrected_cv) / full_cv_inter * 100
    print(f"  CV reduction from EGP correction: {cv_reduction:.1f}%")
else:
    corrected_cv, cv_reduction = np.nan, 0

# ── Success criteria ──────────────────────────────────────────────────────
results = {
    'experiment_id': EXP_ID,
    'title': TITLE,
    'date': datetime.now().isoformat(),
    'user_hypothesized_K': USER_HYPOTHESIZED_K,
    'n_events': int(len(events_df)),
    'n_patients_with_5_events': int(len(patient_stats)),
    'population_isf_peak_mean': float(peak_pop_mean),
    'population_isf_full_mean': float(patient_stats['isf_full_med'].mean()),
    'inter_patient_cv_peak': float(peak_cv_inter),
    'inter_patient_cv_full': float(full_cv_inter),
    'peak_more_uniform': bool(peak_more_uniform),
    'regression_intercept_K_estimate': float(intercept) if not pd.isna(intercept) else None,
    'regression_slope_beta': float(slope) if not pd.isna(slope) else None,
    'regression_var_explained_pct': float(var_explained_pct),
    'cv_reduction_after_egp_correction': float(cv_reduction),
    'distance_from_hypothesized_K': float(peak_pop_mean - USER_HYPOTHESIZED_K),
    'criteria': {
        'P1_peak_more_uniform_than_full': bool(peak_more_uniform),
        'P2_peak_mean_in_50_100': bool(50 <= peak_pop_mean <= 100),
        'P3_egp_correction_reduces_var_30pct': bool(cv_reduction >= 30),
        'P4_slope_in_minus_0.5_to_minus_2': bool(-2.0 <= slope <= -0.5) if not pd.isna(slope) else False,
        'P5_K_intercept_in_50_100': bool(50 <= intercept <= 100) if not pd.isna(intercept) else False,
    },
}
results['n_pass'] = sum(1 for v in results['criteria'].values() if v)
results['pass_count'] = f"{results['n_pass']}/5"

print("\n" + "=" * 70)
print(f"SUCCESS CRITERIA ({results['pass_count']} PASS)")
print("=" * 70)
for k, v in results['criteria'].items():
    print(f"  {'✓' if v else '✗'}  {k}")

out_dir = Path("externals/experiments")
out_path = out_dir / f"exp-{EXP_ID}_formulation_constant.json"
with open(out_path, 'w') as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nSaved: {out_path}")

events_df.to_parquet(out_dir / f"exp-{EXP_ID}_correction_events.parquet")
print(f"Saved events: exp-{EXP_ID}_correction_events.parquet")
