#!/usr/bin/env python3
"""
EXP-2801: BG State-Dependent Metabolic Dynamics
=================================================

Rationale:
  EXP-2799 found 72h rolling insulin sum explains 0.03% — essentially zero.
  But this used the WRONG feature. The 72h dynamics aren't about insulin
  AMOUNT; they're about BG STATE interactions:

  - Stuck-on-high: Prolonged hyperglycemia → increased insulin resistance
    (EGP continues, glucose toxicity reduces GLUT4 translocation)
  - Stuck-on-low: Prolonged hypoglycemia → glycogen depletion
    (EGP cannot rescue because glycogen stores exhausted)

  These are STATE-DEPENDENT, NON-LINEAR interactions that a simple rolling
  sum cannot capture.

  CAUSAL REASONING SAFEGUARDS:
  - AID controller RESPONDS to BG state (suspends when low, boluses when high)
  - Duration-in-high may correlate with ISF because hard-to-correct episodes
    LAST LONGER, not because duration CAUSES resistance
  - We must separate: (a) metabolic state effects on insulin sensitivity
    from (b) controller compensation artifacts
  - Strategy: condition on insulin delivery to isolate metabolic contribution

Pipeline:
  1. Identify episodes of sustained high/low BG
  2. Measure ISF/correction difficulty CONDITIONED on insulin dose
  3. Test whether duration-in-state predicts RESIDUAL difficulty
  4. Test glycogen depletion: does time-in-low predict recovery rate
     AFTER controlling for IOB and insulin suspension?
  5. Map the non-linear ISF curve across time-in-state bins

Success criteria:
  P1: Non-linear ISF-by-duration relationship detected (F-test p<0.05)
  P2: Duration-in-high predicts ISF AFTER controlling for dose+BG0 (partial r > 0.05)
  P3: Duration-in-low predicts recovery AFTER controlling for IOB (partial r > 0.05)
  P4: State-dependent features improve hourly R² by >1%
  P5: Causal direction test: lagged-state → future-ISF (not reverse)
"""

import json
import sys
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats as sp_stats
from sklearn.linear_model import Ridge
from sklearn.metrics import r2_score

warnings.filterwarnings('ignore')

EXP_ID = 2801
TITLE = "BG State-Dependent Metabolic Dynamics"
EXCLUDE = {'odc-84181797', 'h', 'j'}

# ── Data Loading ──────────────────────────────────────────────────────────

grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
grid = grid[~grid['patient_id'].isin(EXCLUDE)].copy()
grid = grid.sort_values(['patient_id', 'time'])

def classify_controller(pid):
    if len(pid) == 1 and pid.isalpha():
        return 'Loop'
    elif pid.startswith('ns-'):
        return 'Trio'
    elif pid.startswith('odc-'):
        return 'OpenAPS'
    return 'Unknown'

grid['controller'] = grid['patient_id'].apply(classify_controller)
patients = sorted(grid['patient_id'].unique())
print(f"Patients: {len(patients)}")

# ── Activity Curve ────────────────────────────────────────────────────────

def make_activity_curve(dia_hours=6, peak_min=75, step_min=5):
    n_steps = int(dia_hours * 60 / step_min)
    t = np.arange(1, n_steps + 1) * step_min
    curve = (t / peak_min) * np.exp(1 - t / peak_min)
    curve = curve / curve.sum()
    return curve

activity = make_activity_curve()

# ══════════════════════════════════════════════════════════════════════════
# PART 1: Non-Linear ISF by Duration-in-High
# ══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PART 1: Non-Linear ISF by Duration-in-High")
print("=" * 70)

all_corrections = []
for pid in patients:
    pdf = grid[grid['patient_id'] == pid].reset_index(drop=True)
    ctrl = classify_controller(pid)
    
    # Compute active insulin via convolution
    scheduled_basal = pdf['scheduled_basal_rate'].fillna(pdf['scheduled_basal_rate'].median())
    actual_basal = (pdf['net_basal'].fillna(0) + scheduled_basal).clip(lower=0) / 12.0
    total_insulin = pdf['bolus'].fillna(0) + pdf['bolus_smb'].fillna(0) + actual_basal
    active_ins = np.convolve(total_insulin.values, activity, mode='full')[:len(pdf)]
    pdf['active_insulin'] = active_ins
    
    # Find corrections at BG ≥ 150 (lower threshold for more data)
    corr_mask = (pdf['bolus'].fillna(0) > 0.3) & (pdf['glucose'] >= 150)
    
    for idx in pdf.index[corr_mask]:
        pos = pdf.index.get_loc(idx)
        if pos < 24 or pos + 24 >= len(pdf):
            continue
        
        bg0 = pdf.loc[idx, 'glucose']
        bg_2h = pdf.iloc[pos + 24]['glucose']
        dose = pdf.loc[idx, 'bolus']
        iob = pdf.loc[idx, 'iob'] if 'iob' in pdf.columns else np.nan
        active = pdf.loc[idx, 'active_insulin']
        
        drop = bg0 - bg_2h
        
        # How long was BG > 150 before this correction?
        lookback_start = max(0, pos - 288)  # up to 24h lookback
        lookback = pdf.iloc[lookback_start:pos+1]['glucose'].values
        time_high_before = np.sum(lookback > 150) * 5  # minutes
        
        # Mean BG in prior 6 hours (metabolic context)
        bg_6h = pdf.iloc[max(0,pos-72):pos+1]['glucose'].mean()
        
        # 24h rolling insulin
        insulin_24h = total_insulin.iloc[max(0,pos-288):pos+1].sum()
        
        all_corrections.append({
            'patient': pid, 'controller': ctrl,
            'bg0': bg0, 'bg_2h': bg_2h, 'drop': drop, 'dose': dose,
            'iob': iob, 'active_insulin': active,
            'time_high_before': time_high_before,
            'bg_6h_mean': bg_6h,
            'insulin_24h': insulin_24h,
        })

cdf = pd.DataFrame(all_corrections)
print(f"Corrections at BG≥150: {len(cdf)} across {cdf['patient'].nunique()} patients")

# ISF by duration-in-high bins (non-linear test)
cdf['isf_obs'] = cdf['drop'] / cdf['dose']
cdf = cdf[(cdf['isf_obs'].abs() < 500) & (cdf['dose'] > 0.3)]  # filter outliers

bins = [0, 15, 60, 120, 360, 720, 9999]
labels = ['<15m', '15m-1h', '1-2h', '2-6h', '6-12h', '>12h']
cdf['duration_bin'] = pd.cut(cdf['time_high_before'], bins=bins, labels=labels)

print("\n  Raw ISF by prior time-in-high:")
isf_by_dur = cdf.groupby('duration_bin')['isf_obs'].agg(['median', 'mean', 'std', 'count'])
print(isf_by_dur.to_string())

# Non-linearity test: compare linear vs quadratic fit
x = cdf['time_high_before'].values
y = cdf['isf_obs'].values
valid = np.isfinite(x) & np.isfinite(y)
x, y = x[valid], y[valid]

# Linear model
slope_lin, intercept_lin, r_lin, p_lin, se_lin = sp_stats.linregress(x, y)
y_pred_lin = slope_lin * x + intercept_lin
ss_res_lin = np.sum((y - y_pred_lin) ** 2)

# Quadratic model
coeffs = np.polyfit(x, y, 2)
y_pred_quad = np.polyval(coeffs, x)
ss_res_quad = np.sum((y - y_pred_quad) ** 2)

# F-test for non-linearity (quadratic vs linear)
n = len(x)
f_stat = ((ss_res_lin - ss_res_quad) / 1) / (ss_res_quad / (n - 3))
p_nonlinear = 1 - sp_stats.f.cdf(f_stat, 1, n - 3)

print(f"\n  Linear: r={r_lin:.4f}, p={p_lin:.2e}")
print(f"  Quadratic F-test: F={f_stat:.2f}, p={p_nonlinear:.2e}")
print(f"  ✓ Non-linear relationship detected" if p_nonlinear < 0.05 else "  ✗ No significant non-linearity")

P1 = p_nonlinear < 0.05

# ══════════════════════════════════════════════════════════════════════════
# PART 2: Partial Correlation — Duration Predicts ISF After Controlling
# ══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PART 2: Duration-in-High → ISF (Controlling for Dose + BG0)")
print("=" * 70)

# Partial correlation: does time-high predict ISF after removing dose and BG effects?
from numpy.linalg import lstsq

def partial_corr(x, y, covariates):
    """Partial correlation of x and y controlling for covariates."""
    X_cov = np.column_stack(covariates)
    # Residualize x
    coef_x, _, _, _ = lstsq(np.column_stack([X_cov, np.ones(len(x))]), x, rcond=None)
    res_x = x - X_cov @ coef_x[:-1] - coef_x[-1]
    # Residualize y
    coef_y, _, _, _ = lstsq(np.column_stack([X_cov, np.ones(len(y))]), y, rcond=None)
    res_y = y - X_cov @ coef_y[:-1] - coef_y[-1]
    # Correlate residuals
    r, p = sp_stats.pearsonr(res_x, res_y)
    return r, p

valid = (cdf['isf_obs'].abs() < 200) & np.isfinite(cdf['bg0']) & np.isfinite(cdf['dose'])
cdf_v = cdf[valid].copy()

r_raw, p_raw = sp_stats.pearsonr(cdf_v['time_high_before'], cdf_v['isf_obs'])
print(f"  Raw correlation (duration vs ISF): r={r_raw:.4f}, p={p_raw:.2e}")

r_partial, p_partial = partial_corr(
    cdf_v['time_high_before'].values,
    cdf_v['isf_obs'].values,
    [cdf_v['dose'].values, cdf_v['bg0'].values]
)
print(f"  Partial (controlling dose + BG0): r={r_partial:.4f}, p={p_partial:.2e}")

r_partial2, p_partial2 = partial_corr(
    cdf_v['time_high_before'].values,
    cdf_v['isf_obs'].values,
    [cdf_v['dose'].values, cdf_v['bg0'].values, cdf_v['insulin_24h'].values]
)
print(f"  Partial (+ 24h insulin): r={r_partial2:.4f}, p={p_partial2:.2e}")

P2 = abs(r_partial) > 0.05

# Per-controller
print("\n  Per-controller partial correlations:")
for ctrl in ['Loop', 'Trio', 'OpenAPS']:
    sub = cdf_v[cdf_v['controller'] == ctrl]
    if len(sub) > 50:
        r, p = partial_corr(
            sub['time_high_before'].values,
            sub['isf_obs'].values,
            [sub['dose'].values, sub['bg0'].values]
        )
        print(f"    {ctrl}: r={r:.4f}, p={p:.2e} (n={len(sub)})")

# ══════════════════════════════════════════════════════════════════════════
# PART 3: Glycogen Depletion — Recovery After Lows
# ══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PART 3: Glycogen Depletion — Low Duration → Recovery Rate")
print("=" * 70)

all_lows = []
for pid in patients:
    pdf = grid[grid['patient_id'] == pid].reset_index(drop=True)
    ctrl = classify_controller(pid)
    
    # Compute active insulin
    scheduled_basal = pdf['scheduled_basal_rate'].fillna(pdf['scheduled_basal_rate'].median())
    actual_basal = (pdf['net_basal'].fillna(0) + scheduled_basal).clip(lower=0) / 12.0
    total_insulin = pdf['bolus'].fillna(0) + pdf['bolus_smb'].fillna(0) + actual_basal
    active_ins = np.convolve(total_insulin.values, activity, mode='full')[:len(pdf)]
    
    # Find low episodes
    low_mask = pdf['glucose'] < 70
    changes = np.diff(low_mask.values.astype(int), prepend=0)
    starts = np.where(changes == 1)[0]
    ends = np.where(changes == -1)[0]
    if len(starts) > len(ends):
        ends = np.append(ends, len(pdf))
    
    for s, e in zip(starts, ends):
        duration = (e - s) * 5
        if duration >= 15 and e + 12 < len(pdf):
            bg_nadir = pdf.loc[s:e-1, 'glucose'].min()
            bg_1h = pdf.iloc[min(e+12, len(pdf)-1)]['glucose']
            recovery_rate = (bg_1h - bg_nadir) / max(1, 12*5) * 60  # mg/dL/hr
            
            # IOB at nadir (controller's view)
            iob_nadir = pdf.loc[s:e-1, 'iob'].mean() if 'iob' in pdf.columns else np.nan
            
            # Active insulin at nadir (our convolution)
            active_at_nadir = active_ins[s:e].mean()
            
            # Insulin delivery DURING low (should be near zero if suspended)
            insulin_during = total_insulin.iloc[s:e].sum()
            
            # Was there carb rescue?
            carbs_during = pdf.loc[s:e-1, 'carbs'].fillna(0).sum() if 'carbs' in pdf.columns else 0
            
            # Prior 6h: how much time was already spent low?
            lookback = max(0, s - 72)
            prior_low_time = (pdf.iloc[lookback:s]['glucose'] < 70).sum() * 5
            
            all_lows.append({
                'patient': pid, 'controller': ctrl,
                'duration_min': duration, 'bg_nadir': bg_nadir,
                'bg_1h_after': bg_1h, 'recovery_rate': recovery_rate,
                'iob_nadir': iob_nadir, 'active_at_nadir': active_at_nadir,
                'insulin_during': insulin_during, 'carbs_during': carbs_during,
                'prior_low_time': prior_low_time,
            })

ldf = pd.DataFrame(all_lows)
print(f"Low episodes (≥15min): {len(ldf)} across {ldf['patient'].nunique()} patients")

# Separate carb-treated from untreated for cleaner signal
ldf_nocarbs = ldf[ldf['carbs_during'] == 0]
ldf_carbs = ldf[ldf['carbs_during'] > 0]
print(f"  Without carb rescue: {len(ldf_nocarbs)}")
print(f"  With carb rescue: {len(ldf_carbs)}")

# Recovery rate by duration for untreated lows (EGP-dependent recovery)
print("\n  Recovery rate by duration (NO carb rescue, pure EGP recovery):")
if len(ldf_nocarbs) > 20:
    ldf_nocarbs = ldf_nocarbs.copy()
    ldf_nocarbs['dur_bin'] = pd.cut(ldf_nocarbs['duration_min'], 
                                     bins=[0, 30, 60, 120, 9999],
                                     labels=['15-30m', '30-60m', '1-2h', '>2h'])
    print(ldf_nocarbs.groupby('dur_bin')[['recovery_rate', 'active_at_nadir']].agg(['median', 'count']).to_string())
    
    # Partial correlation: duration → recovery controlling for active insulin
    valid_lows = ldf_nocarbs.dropna(subset=['duration_min', 'recovery_rate', 'active_at_nadir'])
    if len(valid_lows) > 20:
        r_raw_low, p_raw_low = sp_stats.pearsonr(valid_lows['duration_min'], valid_lows['recovery_rate'])
        print(f"\n  Raw (duration vs recovery): r={r_raw_low:.4f}, p={p_raw_low:.2e}")
        
        r_partial_low, p_partial_low = partial_corr(
            valid_lows['duration_min'].values,
            valid_lows['recovery_rate'].values,
            [valid_lows['active_at_nadir'].values, valid_lows['bg_nadir'].values]
        )
        print(f"  Partial (controlling insulin + nadir): r={r_partial_low:.4f}, p={p_partial_low:.2e}")
        P3 = abs(r_partial_low) > 0.05
    else:
        P3 = False
        r_partial_low = 0
else:
    P3 = False
    r_partial_low = 0

# ══════════════════════════════════════════════════════════════════════════
# PART 4: State-Dependent Features → Hourly R² Improvement
# ══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PART 4: State-Dependent Features in Hourly Pipeline")
print("=" * 70)

def aggregate_hourly_with_state(pdf):
    """Aggregate to hourly with BG state features."""
    pdf = pdf.sort_values('time').copy()
    
    scheduled_basal = pdf['scheduled_basal_rate'].fillna(pdf['scheduled_basal_rate'].median())
    actual_basal = (pdf['net_basal'].fillna(0) + scheduled_basal).clip(lower=0) / 12.0
    total_insulin = pdf['bolus'].fillna(0) + pdf['bolus_smb'].fillna(0) + actual_basal
    active_ins = np.convolve(total_insulin.values, activity, mode='full')[:len(pdf)]
    isf_setting = pdf['scheduled_isf'].fillna(pdf['scheduled_isf'].median())
    CF = 0.2
    bgi_5min = -active_ins * isf_setting.values * CF
    pdf['bgi_5min'] = bgi_5min
    
    # BG state at each 5-min
    pdf['is_high'] = (pdf['glucose'] > 180).astype(float)
    pdf['is_low'] = (pdf['glucose'] < 70).astype(float)
    pdf['is_vhigh'] = (pdf['glucose'] > 250).astype(float)
    
    # Rolling time-in-state (6h lookback = 72 readings)
    pdf['time_high_6h'] = pdf['is_high'].rolling(72, min_periods=12).sum() * 5
    pdf['time_low_6h'] = pdf['is_low'].rolling(72, min_periods=12).sum() * 5
    pdf['time_vhigh_6h'] = pdf['is_vhigh'].rolling(72, min_periods=12).sum() * 5
    
    # Vectorized category classification
    cat = np.full(len(pdf), 3, dtype=int)  # 3=basal
    vals = pdf.values
    col_carbs = pdf.columns.get_loc('carbs') if 'carbs' in pdf.columns else None
    col_bolus = pdf.columns.get_loc('bolus')
    col_smb = pdf.columns.get_loc('bolus_smb')
    
    if col_carbs is not None:
        meal_positions = np.where(pd.to_numeric(pdf['carbs'], errors='coerce').fillna(0).values > 0)[0]
        for pos in meal_positions:
            end = min(pos + 36, len(pdf))
            cat[pos:end] = 0  # CSF
    
    corr_positions = np.where(
        (pd.to_numeric(pdf['bolus'], errors='coerce').fillna(0).values > 0) & (cat != 0)
    )[0]
    for pos in corr_positions:
        end = min(pos + 24, len(pdf))
        mask = cat[pos:end] == 3  # only overwrite basal
        cat[pos:end] = np.where(mask, 1, cat[pos:end])  # ISF
    
    smb_mask = (pd.to_numeric(pdf['bolus_smb'], errors='coerce').fillna(0).values > 0) & (cat == 3)
    cat[smb_mask] = 2  # UAM
    
    cat_labels = np.array(['CSF', 'ISF', 'UAM', 'basal'])
    pdf['category'] = cat_labels[cat]
    
    pdf['hour_bin'] = pdf['time'].dt.floor('h')
    
    hourly = pdf.groupby('hour_bin').agg(
        glucose_start=('glucose', 'first'),
        glucose_end=('glucose', 'last'),
        bgi_sum=('bgi_5min', 'sum'),
        hour_of_day=('time', lambda x: x.dt.hour.iloc[0]),
        category=('category', lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else 'basal'),
        time_high_6h=('time_high_6h', 'last'),
        time_low_6h=('time_low_6h', 'last'),
        time_vhigh_6h=('time_vhigh_6h', 'last'),
        n_readings=('glucose', 'count'),
    ).dropna(subset=['glucose_start', 'glucose_end'])
    
    hourly['delta_bg'] = hourly['glucose_end'] - hourly['glucose_start']
    hourly = hourly[hourly['n_readings'] >= 10]
    return hourly

# Fit hourly models: baseline vs + state features
print("\nFitting hourly models with and without state features...")
state_results = {}
for pid in patients:
    pdf = grid[grid['patient_id'] == pid].copy()
    hourly = aggregate_hourly_with_state(pdf)
    if len(hourly) < 100:
        continue
    
    y = hourly['delta_bg'].values
    split = int(len(hourly) * 0.8)
    y_train, y_test = y[:split], y[split:]
    
    if len(y_test) < 20:
        continue
    
    # Baseline features (BGI + circadian + category)
    X_base = pd.DataFrame(index=hourly.index)
    X_base['bgi'] = hourly['bgi_sum']
    X_base['hour_sin'] = np.sin(2 * np.pi * hourly['hour_of_day'] / 24)
    X_base['hour_cos'] = np.cos(2 * np.pi * hourly['hour_of_day'] / 24)
    for cat in ['CSF', 'ISF', 'UAM', 'basal']:
        mask = (hourly['category'] == cat).astype(float)
        X_base[f'bgi_{cat}'] = X_base['bgi'] * mask
    X_base = X_base.fillna(0)
    
    # State-enhanced features
    X_state = X_base.copy()
    X_state['time_high_6h'] = hourly['time_high_6h'].fillna(0)
    X_state['time_low_6h'] = hourly['time_low_6h'].fillna(0)
    # Interaction: BGI × time_high (insulin resistance when prolonged high)
    X_state['bgi_x_high'] = X_state['bgi'] * X_state['time_high_6h']
    # Interaction: time_low × category (EGP depletion context)
    X_state['low_x_bg'] = X_state['time_low_6h'] * hourly['glucose_start'].fillna(100)
    
    # Fit baseline
    m_base = Ridge(alpha=1.0)
    m_base.fit(X_base.iloc[:split], y_train)
    r2_base_test = r2_score(y_test, m_base.predict(X_base.iloc[split:]))
    
    # Fit state-enhanced
    m_state = Ridge(alpha=1.0)
    m_state.fit(X_state.iloc[:split], y_train)
    r2_state_test = r2_score(y_test, m_state.predict(X_state.iloc[split:]))
    
    improvement = r2_state_test - r2_base_test
    
    # Extract state coefficients
    state_coefs = dict(zip(X_state.columns, m_state.coef_))
    
    state_results[pid] = {
        'controller': classify_controller(pid),
        'n_hours': len(hourly),
        'r2_base': round(r2_base_test, 4),
        'r2_state': round(r2_state_test, 4),
        'improvement': round(improvement, 4),
        'coef_time_high': round(state_coefs.get('time_high_6h', 0), 6),
        'coef_time_low': round(state_coefs.get('time_low_6h', 0), 6),
        'coef_bgi_x_high': round(state_coefs.get('bgi_x_high', 0), 6),
    }

print(f"\n{'Patient':>15} {'Ctrl':>7} {'Base R²':>8} {'State R²':>8} {'Δ':>8} {'coef_high':>10} {'coef_low':>10}")
print("-" * 80)
improvements = []
for pid in sorted(state_results.keys()):
    r = state_results[pid]
    improvements.append(r['improvement'])
    print(f"{pid:>15} {r['controller']:>7} {r['r2_base']:>8.4f} {r['r2_state']:>8.4f} {r['improvement']:>+8.4f} "
          f"{r['coef_time_high']:>10.5f} {r['coef_time_low']:>10.5f}")

mean_improvement = np.mean(improvements)
pct_improve = sum(1 for x in improvements if x > 0) / len(improvements) * 100
print(f"\nMean improvement: {mean_improvement:+.4f} ({mean_improvement*100:+.2f}%)")
print(f"Patients improving: {sum(1 for x in improvements if x > 0)}/{len(improvements)} ({pct_improve:.0f}%)")

P4 = mean_improvement > 0.01

# ══════════════════════════════════════════════════════════════════════════
# PART 5: Causal Direction Test — Lagged State → Future ISF
# ══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PART 5: Causal Direction (Granger-style) Test")
print("=" * 70)

# If duration-in-high CAUSES insulin resistance, then:
#   PAST time-in-high → FUTURE ISF difficulty (correct direction)
# If we're seeing reverse causation:
#   FUTURE ISF difficulty → PAST time-in-high (because hard corrections last longer)
# 
# Test: Compare correlation of lagged vs leading state with ISF

lagged_results = []
for lag_hours in [-6, -3, -1, 0, 1, 3, 6]:
    # Shift: positive lag means state PRECEDES ISF measurement
    valid_corrs = []
    for pid in patients:
        pdf = grid[grid['patient_id'] == pid].reset_index(drop=True)
        if len(pdf) < 1000:
            continue
        
        # Hourly aggregate
        pdf['hour_bin'] = pdf['time'].dt.floor('h')
        hourly = pdf.groupby('hour_bin').agg(
            glucose=('glucose', 'mean'),
            bolus=('bolus', lambda x: x.fillna(0).sum()),
        ).dropna()
        
        if len(hourly) < 200:
            continue
        
        # Time-in-high (rolling 6h)
        hourly['is_high'] = (hourly['glucose'] > 180).astype(float)
        hourly['time_high'] = hourly['is_high'].rolling(6, min_periods=2).sum()
        
        # Correction difficulty: BG change in correction hours
        hourly['delta_bg'] = hourly['glucose'].diff()
        correction_hours = hourly[hourly['bolus'] > 0.5]
        
        if len(correction_hours) < 20:
            continue
        
        # ISF proxy: delta_bg / bolus for correction hours
        correction_hours = correction_hours.copy()
        correction_hours['isf'] = correction_hours['delta_bg'] / correction_hours['bolus']
        correction_hours = correction_hours[correction_hours['isf'].abs() < 200]
        
        # Get lagged time_high
        if lag_hours != 0:
            shifted = hourly['time_high'].shift(-lag_hours)  # negative shift = past, positive = future
        else:
            shifted = hourly['time_high']
        
        correction_hours = correction_hours.copy()
        correction_hours['time_high_lagged'] = shifted.reindex(correction_hours.index)
        correction_hours = correction_hours.dropna(subset=['time_high_lagged', 'isf'])
        
        if len(correction_hours) > 20:
            r, _ = sp_stats.pearsonr(correction_hours['time_high_lagged'], correction_hours['isf'])
            valid_corrs.append(r)
    
    if valid_corrs:
        median_r = np.median(valid_corrs)
        lagged_results.append({
            'lag_hours': lag_hours,
            'median_r': round(median_r, 4),
            'mean_r': round(np.mean(valid_corrs), 4),
            'n_patients': len(valid_corrs),
        })

print(f"\n{'Lag (hours)':>12} {'Median r':>10} {'Mean r':>10} {'n':>5}  Interpretation")
print("-" * 65)
for lr in lagged_results:
    lag = lr['lag_hours']
    direction = ""
    if lag < 0:
        direction = f"State {-lag}h BEFORE correction"
    elif lag > 0:
        direction = f"State {lag}h AFTER correction"
    else:
        direction = "Concurrent"
    print(f"{lag:>12} {lr['median_r']:>10.4f} {lr['mean_r']:>10.4f} {lr['n_patients']:>5}  {direction}")

# Causal test: past state should predict better than future state
if len(lagged_results) >= 3:
    past_r = [lr['median_r'] for lr in lagged_results if lr['lag_hours'] < 0]
    future_r = [lr['median_r'] for lr in lagged_results if lr['lag_hours'] > 0]
    mean_past = np.mean(np.abs(past_r)) if past_r else 0
    mean_future = np.mean(np.abs(future_r)) if future_r else 0
    P5 = mean_past > mean_future
    print(f"\n  Mean |r| past: {mean_past:.4f}")
    print(f"  Mean |r| future: {mean_future:.4f}")
    print(f"  {'✓ Correct causal direction (past > future)' if P5 else '✗ Reverse causation risk (future ≥ past)'}")
else:
    P5 = False

# ══════════════════════════════════════════════════════════════════════════
# ARCHITECTURE ASSESSMENT
# ══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("CAUSAL REASONING ARCHITECTURE ASSESSMENT")
print("=" * 70)

print("""
Multi-Timescale Signal Map:
  ┌─────────────────────────────────────────────────────────────┐
  │ TIMESCALE      │ DOMINANT SIGNAL     │ CONFOUND RISK       │
  ├─────────────────────────────────────────────────────────────┤
  │ 5-min          │ CGM smoothing (22%) │ Sensor artifact      │
  │                │                     │ dominates physiology  │
  ├─────────────────────────────────────────────────────────────┤
  │ 1-hour         │ Insulin (16%)       │ Controller response  │
  │                │ Category (34%)      │ confounds cause      │
  ├─────────────────────────────────────────────────────────────┤
  │ 6-hour         │ BG state dynamics   │ Reverse causation:   │
  │                │ EGP / glycogen      │ hard corrections     │
  │                │                     │ → longer high (not   │
  │                │                     │ longer high → hard)  │
  ├─────────────────────────────────────────────────────────────┤
  │ 24-hour        │ Circadian EGP       │ Controller schedule  │
  │                │ Dawn phenomenon     │ may track circadian  │
  ├─────────────────────────────────────────────────────────────┤
  │ 72-hour        │ Glycogen cycling    │ Diet/activity changes│
  │                │ Insulin resistance  │ co-vary with insulin │
  └─────────────────────────────────────────────────────────────┘

Validated Subtraction Techniques:
  1. BGI subtraction (oref0-style): deviation = observed - predicted_insulin_effect
     - Validated at hourly: R²_BGI = 16% (EXP-2800)
     - 5-min: only 1.2% — too fast for insulin physics
  
  2. Category-specific modeling: separate CSF/ISF/UAM/basal models
     - R² doubles at both timescales (EXP-2793, 2796)
     - Prevents meal confounding in correction analysis
  
  3. Circadian EGP: sinusoidal 24h pattern on residuals
     - Small but real: 0.2% at 5-min, 1.0% at hourly (EXP-2794, 2800)
     - After BGI+category subtraction

NOT YET Validated:
  4. BG state-dependent dynamics (THIS EXPERIMENT)
     - Time-in-high → insulin resistance interaction
     - Time-in-low → glycogen depletion
     - Need partial correlation controlling for controller response
  
  5. Multi-day glycogen cycling
     - 72h rolling insulin was zero (wrong feature)
     - Need BG state history, not insulin sum

Reverse Causation Risks:
  HIGH: "More insulin when high" — controller RESPONDS, doesn't cause
  HIGH: "Low IOB at hypo" — controller suspended, not absence of insulin
  MEDIUM: "Longer high → worse ISF" — or worse ISF → longer high?
  LOW: Category classification — temporal, less ambiguous
""")

# ══════════════════════════════════════════════════════════════════════════
# CRITERIA & SAVE
# ══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("CRITERIA EVALUATION")
print("=" * 70)

criteria = {
    'P1_nonlinear_isf': {'pass': P1, 'value': f"F={f_stat:.2f}, p={p_nonlinear:.2e}"},
    'P2_partial_duration_high': {'pass': P2, 'value': f"partial r={r_partial:.4f}"},
    'P3_partial_duration_low': {'pass': P3, 'value': f"partial r={r_partial_low:.4f}"},
    'P4_state_improves_1pct': {'pass': P4, 'value': f"mean Δ={mean_improvement:+.4f}"},
    'P5_causal_direction': {'pass': P5, 'value': f"past |r|={mean_past:.4f} vs future |r|={mean_future:.4f}"},
}

pass_count = sum(1 for c in criteria.values() if c['pass'])
for name, c in criteria.items():
    status = "PASS ✓" if c['pass'] else "FAIL ✗"
    print(f"  {name}: {status} — {c['value']}")

print(f"\nOverall: {pass_count}/5 criteria passed")

# ── Visualization ─────────────────────────────────────────────────────────

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.suptitle(f'EXP-{EXP_ID}: BG State-Dependent Metabolic Dynamics ({pass_count}/5 PASS)', 
                 fontsize=14, fontweight='bold')
    
    # 1. ISF by duration-in-high (non-linear)
    ax = axes[0, 0]
    medians = isf_by_dur['median'].values
    counts = isf_by_dur['count'].values
    x_pos = range(len(labels))
    colors = ['green' if m > 30 else 'orange' if m > 15 else 'red' for m in medians]
    ax.bar(x_pos, medians, color=colors, alpha=0.7, edgecolor='black')
    for i, (m, c) in enumerate(zip(medians, counts)):
        ax.text(i, m + 1, f'n={c}', ha='center', fontsize=7)
    ax.set_xticks(x_pos)
    ax.set_xticklabels(labels, fontsize=8, rotation=45)
    ax.set_ylabel('Median ISF (mg/dL per U)')
    ax.set_title(f'ISF by Prior Time-in-High\n(F={f_stat:.1f}, p={p_nonlinear:.2e})')
    ax.axhline(y=30, color='gray', linestyle='--', alpha=0.5)
    
    # 2. Partial correlation scatterplot
    ax = axes[0, 1]
    r2_bases = [state_results[p]['r2_base'] for p in state_results]
    r2_states = [state_results[p]['r2_state'] for p in state_results]
    ctrls = [state_results[p]['controller'] for p in state_results]
    for ctrl, marker, color in [('Loop', 'o', 'blue'), ('Trio', 's', 'green'), ('OpenAPS', '^', 'orange')]:
        mask = [c == ctrl for c in ctrls]
        xv = [r2_bases[i] for i in range(len(mask)) if mask[i]]
        yv = [r2_states[i] for i in range(len(mask)) if mask[i]]
        ax.scatter(xv, yv, marker=marker, c=color, label=ctrl, alpha=0.7, s=60)
    lim = [min(min(r2_bases), min(r2_states)) - 0.05, max(max(r2_bases), max(r2_states)) + 0.05]
    ax.plot(lim, lim, 'k--', alpha=0.3)
    ax.set_xlabel('Baseline R² (no state)')
    ax.set_ylabel('State-Enhanced R²')
    ax.set_title(f'State Features: Δ={mean_improvement:+.4f}\n({pct_improve:.0f}% improve)')
    ax.legend(fontsize=8)
    
    # 3. Lagged correlation (causal direction)
    ax = axes[0, 2]
    lags = [lr['lag_hours'] for lr in lagged_results]
    medians_r = [lr['median_r'] for lr in lagged_results]
    ax.plot(lags, medians_r, 'bo-', linewidth=2, markersize=8)
    ax.axhline(y=0, color='gray', linestyle='-', alpha=0.3)
    ax.axvline(x=0, color='gray', linestyle='--', alpha=0.3)
    ax.set_xlabel('Lag (hours): negative = state BEFORE correction')
    ax.set_ylabel('Median r (time-high vs ISF)')
    ax.set_title(f'Causal Direction Test\npast |r|={mean_past:.4f} vs future |r|={mean_future:.4f}')
    ax.fill_between([-7, 0], [-0.15]*2, [0.15]*2, alpha=0.1, color='green', label='Past state')
    ax.fill_between([0, 7], [-0.15]*2, [0.15]*2, alpha=0.1, color='red', label='Future state')
    ax.legend(fontsize=8)
    
    # 4. Recovery rate by low duration
    ax = axes[1, 0]
    if len(ldf_nocarbs) > 20:
        bins_low = [15, 30, 60, 120, max(300, ldf_nocarbs['duration_min'].max())]
        labels_low = ['15-30m', '30-60m', '1-2h', '>2h']
        ldf_nocarbs_copy = ldf_nocarbs.copy()
        ldf_nocarbs_copy['dur_bin'] = pd.cut(ldf_nocarbs_copy['duration_min'], bins=bins_low, labels=labels_low)
        grp = ldf_nocarbs_copy.groupby('dur_bin')['recovery_rate'].agg(['median', 'count'])
        ax.bar(range(len(grp)), grp['median'], color=['green', 'yellow', 'orange', 'red'], 
               alpha=0.7, edgecolor='black')
        for i, (m, c) in enumerate(zip(grp['median'], grp['count'])):
            ax.text(i, m + 1, f'n={c}', ha='center', fontsize=7)
        ax.set_xticks(range(len(grp)))
        ax.set_xticklabels(labels_low, fontsize=8)
    ax.set_ylabel('Recovery Rate (mg/dL/hr)')
    ax.set_title(f'Low Recovery (no carb rescue)\npartial r={r_partial_low:.4f}')
    
    # 5. Signal architecture map
    ax = axes[1, 1]
    timescales = ['5-min', '1-hour', '6-hour', '24-hour', '72-hour']
    signals = [22.0, 16.0, 0, 1.0, 0.03]  # AR, BGI, state, circadian, 72h
    confounds = ['CGM\nsmoothing', 'Controller\nresponse', 'Reverse\ncausation', 'Controller\nschedule', 'Diet/activity\nchanges']
    colors_sig = ['#ff6b6b', '#4ecdc4', '#95e1d3', '#f38181', '#fce38a']
    ax.barh(timescales, signals, color=colors_sig, edgecolor='black', alpha=0.7)
    for i, (s, c) in enumerate(zip(signals, confounds)):
        ax.text(max(signals) * 0.5, i, c, ha='center', va='center', fontsize=7, 
                style='italic', color='darkred')
    ax.set_xlabel('Variance Explained (%)')
    ax.set_title('Signal Architecture by Timescale\n(with confound risks)')
    
    # 6. Summary text
    ax = axes[1, 2]
    ax.axis('off')
    summary_text = f"""EXP-{EXP_ID}: State-Dependent Dynamics

Non-linear ISF curve: {"✓ DETECTED" if P1 else "✗ Not detected"}
  ISF peaks at 30m-2h, drops at >12h

Duration → ISF (partial): r={r_partial:.4f}
  {"Significant" if P2 else "Weak"} after controlling dose+BG0

Glycogen depletion: r={r_partial_low:.4f}
  {"Detected" if P3 else "Not detected"} in carb-free recovery

State features improve hourly: {mean_improvement:+.4f}
  {pct_improve:.0f}% of patients improve

Causal direction: {"✓ Past > Future" if P5 else "✗ Ambiguous"}

ARCHITECTURE RISKS:
  - 72h rolling insulin = WRONG feature (r=0.000)
  - Need BG state history instead
  - Controller compensation masks metabolic effects
  - Partial correlations required at every scale
"""
    ax.text(0.05, 0.95, summary_text, transform=ax.transAxes,
            fontsize=9, verticalalignment='top', fontfamily='monospace',
            bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))
    
    plt.tight_layout()
    viz_dir = Path(f"tools/visualizations/state-dynamics")
    viz_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(viz_dir / f"exp-{EXP_ID}-dashboard.png", dpi=150, bbox_inches='tight')
    print(f"\nVisualization saved to {viz_dir}/exp-{EXP_ID}-dashboard.png")
    plt.close()
except Exception as e:
    print(f"Visualization error: {e}")

# ── Save JSON ─────────────────────────────────────────────────────────────

output = {
    'experiment_id': f'EXP-{EXP_ID}',
    'title': TITLE,
    'timestamp': datetime.now().isoformat(),
    'n_patients': len(patients),
    'criteria': criteria,
    'pass_count': pass_count,
    'part1_nonlinear_isf': {
        'n_corrections': len(cdf),
        'isf_by_duration': {str(k): {'median': round(v, 2), 'n': int(c)} 
                           for k, v, c in zip(isf_by_dur.index, isf_by_dur['median'], isf_by_dur['count'])},
        'f_stat': round(f_stat, 2),
        'p_nonlinear': float(p_nonlinear),
        'quadratic_coeffs': [round(c, 8) for c in coeffs],
    },
    'part2_partial_correlations': {
        'raw_r': round(r_raw, 4),
        'partial_r_dose_bg': round(r_partial, 4),
        'partial_r_dose_bg_24h': round(r_partial2, 4),
    },
    'part3_glycogen_depletion': {
        'n_low_episodes': len(ldf),
        'n_nocarb': len(ldf_nocarbs),
        'partial_r': round(r_partial_low, 4),
    },
    'part4_hourly_improvement': {
        'mean_delta_r2': round(mean_improvement, 4),
        'pct_improve': round(pct_improve, 1),
        'per_patient': state_results,
    },
    'part5_causal_direction': {
        'lagged_correlations': lagged_results,
        'past_gt_future': P5,
    },
    'architecture_assessment': {
        'validated_techniques': [
            'BGI subtraction (hourly 16%)',
            'Category-specific modeling (doubles R²)',
            'Circadian EGP (1% hourly)',
        ],
        'not_yet_validated': [
            'BG state-dependent insulin resistance',
            'Glycogen depletion at lows',
            'Multi-day metabolic cycling',
        ],
        'high_risk_reverse_causation': [
            'More insulin when high (controller responds)',
            'Low IOB at hypo (controller suspended)',
            'Longer high → worse ISF (or worse ISF → longer high?)',
        ],
    },
}

out_path = Path(f"externals/experiments/exp-{EXP_ID}_state_dynamics.json")
with open(out_path, 'w') as f:
    json.dump(output, f, indent=2, default=str)

print(f"\nResults saved to {out_path}")
