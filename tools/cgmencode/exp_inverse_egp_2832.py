#!/usr/bin/env python3
"""
EXP-2832: Inverse EGP Estimation (Expand Coverage 11 → 28)
============================================================

Problem: Canonical EGP audit (EXP-2820) only credentialed 11 of 28 patients
because two independent methods needed to agree. The other 17 lack a usable
EGP estimate, blocking multi-layer correction for the majority of patients.

Approach: Use the calibrated relationship between observed correction-event
ISF and canonical EGP (from the 11 audit-credentialed patients) to invert
and estimate EGP for the remaining 17.

Calibration model (from EXP-2831 within-patient regression):
  ISF_obs ≈ K_patient + β_egp × (EGP × t / dose) + β_wear × wear + noise

We learned β_egp ≈ +1.65 (positive coefficient — patients with higher EGP
have HIGHER apparent ISF in correction events, opposite of formulation
hypothesis but consistent with the empirical pattern).

The simpler between-patient relationship:
  EGP_canonical[i] vs <ISF_obs>[i] across the 11 calibrated patients
  → fit linear model
  → invert to predict EGP for the 17 uncalibrated patients

Cross-validation:
  Leave-one-out across 11 calibrated patients to estimate the prediction
  error band before extrapolating to 17.

Sanity checks:
  - State proxy (EXP-2823): %State1 ↔ EGP relationship (ρ=+0.54)
  - Predicted EGPs should be in plausible biological range (0-30 mg/dL/hr)
  - Extreme outlier patients (very high or very low ISF) may indicate
    extrapolation risk; flag those

Success criteria:
  P1: LOO calibration MAE < 50% of canonical EGP standard deviation
  P2: All 17 inverse estimates within plausible range [0, 30] mg/dL/hr
  P3: Inverse EGP correlates with state proxy (ρ > 0.3)
  P4: Inverse EGP improves wear-corrected ISF residual variance
       for the 17 expanded patients
  P5: Combined 28-patient EGP distribution has reasonable spread
       (population CV < 1.5)
"""

import json
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats as sp_stats
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import LeaveOneOut

warnings.filterwarnings('ignore')

EXP_ID = 2832
TITLE = "Inverse EGP Estimation"
EXCLUDE = {'odc-84181797', 'h', 'j'}

print(f"[EXP-{EXP_ID}] {TITLE}")
print("=" * 70)

# ── Data ─────────────────────────────────────────────────────────────────
events = pd.read_parquet("externals/experiments/exp-2830_correction_events.parquet")
canonical_egp = pd.read_parquet("externals/experiments/exp-2820_canonical_egp.parquet")
state = pd.read_parquet("externals/experiments/exp-2810_state_assignments.parquet")

# Per-patient median ISF (from correction events, full window)
patient_isf = events.groupby('patient_id').agg(
    n=('isf_full', 'count'),
    isf_med=('isf_full', 'median'),
    isf_mean=('isf_full', 'mean'),
).reset_index()
patient_isf = patient_isf[patient_isf['n'] >= 5]
print(f"Patients with ≥5 correction events: {len(patient_isf)}")

# State percentage per patient
state_pct = state.groupby('patient_id')['state'].apply(lambda x: (x == 1).mean()).reset_index()
state_pct.columns = ['patient_id', 'pct_state1']

# Merge
df = patient_isf.merge(canonical_egp[['patient_id', 'canonical_egp_mg_dL_hr']], on='patient_id', how='left')
df = df.merge(state_pct, on='patient_id', how='left')

# Calibrated subset (have canonical EGP)
calib = df.dropna(subset=['canonical_egp_mg_dL_hr']).copy()
target = df[df['canonical_egp_mg_dL_hr'].isna()].copy()
print(f"  Calibrated (have canonical EGP): {len(calib)}")
print(f"  Target (need inverse estimate):  {len(target)}")

# ── Build calibration model ──────────────────────────────────────────────
# Use both ISF_med and pct_state1 as predictors (state proxy from EXP-2823)
print("\n── Calibration model (canonical EGP ~ ISF_med + pct_state1) ──")
features = ['isf_med', 'pct_state1']
calib_clean = calib.dropna(subset=features + ['canonical_egp_mg_dL_hr'])
print(f"  Calibration n: {len(calib_clean)}")

X = calib_clean[features].values
y = calib_clean['canonical_egp_mg_dL_hr'].values

reg = LinearRegression().fit(X, y)
y_pred = reg.predict(X)
r2 = 1 - np.var(y - y_pred) / np.var(y)
print(f"  In-sample R²: {r2*100:.1f}%")
print(f"  intercept: {reg.intercept_:.3f}")
for f, c in zip(features, reg.coef_):
    print(f"  β_{f}: {c:+.4f}")

# ── LOO cross-validation ─────────────────────────────────────────────────
print("\n── Leave-one-out cross-validation ──")
loo = LeaveOneOut()
errors = []
predictions_loo = []
for train_idx, test_idx in loo.split(X):
    reg_loo = LinearRegression().fit(X[train_idx], y[train_idx])
    pred = reg_loo.predict(X[test_idx])[0]
    actual = y[test_idx][0]
    errors.append(abs(pred - actual))
    predictions_loo.append({
        'patient_id': calib_clean.iloc[test_idx[0]]['patient_id'],
        'actual': float(actual),
        'predicted': float(pred),
        'error': float(abs(pred - actual)),
    })

mae = np.mean(errors)
y_std = np.std(y)
print(f"  LOO MAE: {mae:.2f} mg/dL/hr")
print(f"  Canonical EGP std: {y_std:.2f}")
print(f"  MAE / std: {mae / y_std * 100:.1f}%")
print(f"\n  Per-patient LOO predictions:")
for p in sorted(predictions_loo, key=lambda x: x['actual']):
    print(f"    {p['patient_id']:<25} actual={p['actual']:>5.1f}  pred={p['predicted']:>5.1f}  err={p['error']:>5.1f}")

# ── Apply to target patients ─────────────────────────────────────────────
print("\n── Inverse EGP for uncalibrated patients ──")
target_clean = target.dropna(subset=features).copy()
print(f"  Target patients with all features: {len(target_clean)}")
X_target = target_clean[features].values
target_clean['inverse_egp'] = reg.predict(X_target)
# Clip to plausible range
target_clean['inverse_egp_clipped'] = target_clean['inverse_egp'].clip(0, 30)
target_clean['extrapolation_flag'] = (target_clean['inverse_egp'] != target_clean['inverse_egp_clipped'])

print(f"\n  {'patient':<25} {'isf_med':>8} {'pct_S1':>7} {'inverse_egp':>12} {'flag':>6}")
for _, row in target_clean.sort_values('inverse_egp').iterrows():
    print(f"  {row['patient_id']:<25} {row['isf_med']:>8.1f} {row['pct_state1']*100:>6.1f}% "
          f"{row['inverse_egp']:>12.2f} {'EXTRA' if row['extrapolation_flag'] else '':>6}")

n_extrap = int(target_clean['extrapolation_flag'].sum())
n_in_range = int((~target_clean['extrapolation_flag']).sum())
print(f"\n  In range [0, 30]: {n_in_range}/{len(target_clean)}")
print(f"  Extrapolated: {n_extrap}")

# ── Sanity check: state proxy correlation ────────────────────────────────
print("\n── Sanity: inverse EGP vs state proxy ──")
if len(target_clean) >= 5:
    rho_state, p_state = sp_stats.spearmanr(target_clean['pct_state1'],
                                              target_clean['inverse_egp'])
    print(f"  Spearman ρ(pct_state1, inverse_egp) = {rho_state:+.3f} (p={p_state:.3f})")
else:
    rho_state = np.nan

# ── Combined 28-patient EGP distribution ─────────────────────────────────
combined_egp = pd.concat([
    calib[['patient_id', 'canonical_egp_mg_dL_hr']].rename(columns={'canonical_egp_mg_dL_hr': 'egp'}).assign(source='canonical'),
    target_clean[['patient_id', 'inverse_egp_clipped']].rename(columns={'inverse_egp_clipped': 'egp'}).assign(source='inverse'),
])
print(f"\n── Combined EGP distribution ──")
print(f"  N patients: {len(combined_egp)}")
print(f"  Median EGP: {combined_egp['egp'].median():.2f} mg/dL/hr")
print(f"  Mean EGP:   {combined_egp['egp'].mean():.2f}")
print(f"  Std EGP:    {combined_egp['egp'].std():.2f}")
print(f"  CV:         {combined_egp['egp'].std() / combined_egp['egp'].mean():.3f}")
pop_cv = combined_egp['egp'].std() / combined_egp['egp'].mean()

# ── Variance reduction test ──────────────────────────────────────────────
print("\n── Variance reduction with extended EGP ──")
inv_egp_map = dict(zip(target_clean['patient_id'], target_clean['inverse_egp_clipped']))
canon_map = dict(zip(canonical_egp['patient_id'], canonical_egp['canonical_egp_mg_dL_hr']))
all_egp = {**canon_map, **inv_egp_map}

ev = events.copy()
ev['egp_extended'] = ev['patient_id'].map(all_egp)
ev_target = ev[ev['patient_id'].isin(target_clean['patient_id'])].dropna(subset=['egp_extended', 'isf_full'])
print(f"  Events for target patients with extended EGP: {len(ev_target)}")

if len(ev_target) >= 30:
    # Within-patient demean
    ev_target['isf_dm'] = ev_target['isf_full'] - ev_target.groupby('patient_id')['isf_full'].transform('mean')
    ev_target['burden'] = ev_target['egp_extended'] * 3.0 / ev_target['dose']
    ev_target['burden_dm'] = ev_target['burden'] - ev_target.groupby('patient_id')['burden'].transform('mean')
    if ev_target['burden_dm'].std() > 1e-6:
        slope, _, r, p, _ = sp_stats.linregress(ev_target['burden_dm'], ev_target['isf_dm'])
        print(f"  Inverse EGP burden ~ ISF_dm: r={r:+.3f} (p={p:.4f})")
        target_var_improvement = r**2 * 100
    else:
        target_var_improvement = 0
        print("  burden_dm has zero variance (likely all patients have same constant inverse EGP)")
else:
    target_var_improvement = 0

# ── Success criteria ──────────────────────────────────────────────────────
results = {
    'experiment_id': EXP_ID,
    'title': TITLE,
    'date': datetime.now().isoformat(),
    'n_calibration': int(len(calib_clean)),
    'n_target': int(len(target_clean)),
    'n_extended_total': int(len(combined_egp)),
    'in_sample_R2_pct': float(r2 * 100),
    'loo_mae': float(mae),
    'canonical_egp_std': float(y_std),
    'mae_over_std_pct': float(mae / y_std * 100),
    'n_extrapolated': int(n_extrap),
    'rho_state_proxy': float(rho_state) if not pd.isna(rho_state) else None,
    'population_egp_cv': float(pop_cv),
    'target_var_improvement_pct': float(target_var_improvement),
    'criteria': {
        'P1_LOO_MAE_below_50pct_std': bool(mae / y_std < 0.5),
        'P2_all_in_plausible_range': bool(n_extrap == 0),
        'P3_correlates_with_state_proxy': bool(abs(rho_state) > 0.3) if not pd.isna(rho_state) else False,
        'P4_target_variance_improves': bool(target_var_improvement > 5),
        'P5_combined_CV_below_1.5': bool(pop_cv < 1.5),
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
with open(out_dir / f"exp-{EXP_ID}_inverse_egp.json", 'w') as f:
    json.dump(results, f, indent=2, default=str)
combined_egp.to_parquet(out_dir / f"exp-{EXP_ID}_extended_egp.parquet")
print(f"\nSaved: exp-{EXP_ID}_inverse_egp.json")
print(f"Saved extended EGP: exp-{EXP_ID}_extended_egp.parquet ({len(combined_egp)} patients)")
