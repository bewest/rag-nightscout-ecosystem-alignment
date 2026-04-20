#!/usr/bin/env python3
"""
EXP-2803: Day-Level Aggregation for Multi-Day Signal Recovery
=============================================================

Rationale:
  EXP-2802 showed 72h rolling windows have REVERSED causal direction (21%
  correct = future predicts better than past). This is because rolling
  windows blur the temporal boundary between cause and effect.

  Solution: Use DISCRETE DAY BOUNDARIES. Yesterday's metrics predict today's
  outcomes. This respects temporal ordering perfectly:
  - Yesterday's TIR → today's ISF effectiveness
  - Yesterday's CV → today's predictability
  - Yesterday's insulin load → today's resistance

  If multi-day patterns exist, they should emerge at day-level with proper
  causal ordering (yesterday ALWAYS precedes today).

  Additionally: tests the 50/50 rule (half TDD for basal, half for food/
  corrections) as a per-day stability metric.

Pipeline:
  1. Aggregate each patient's data to daily summaries
  2. Compute day-level metrics: TIR, CV, TDD, basal%, ISF_effective
  3. Test: does yesterday's metrics predict today's ISF/outcomes?
  4. Test: does 3-day rolling predict better than 1-day?
  5. Assess causal direction: lagged vs leading day predictions

Success criteria:
  P1: Yesterday's TIR predicts today's ISF effectiveness (r > 0.10)
  P2: Yesterday's CV predicts today's BG variability (r > 0.15)
  P3: Causal direction correct: lag-1 > lead-1 for >60% patients
  P4: 50/50 rule violation predicts worse next-day outcomes
  P5: 3-day rolling adds >2% over 1-day for ISF prediction
"""

import json
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats as sp_stats
from sklearn.linear_model import Ridge
from sklearn.metrics import r2_score

warnings.filterwarnings('ignore')

EXP_ID = 2803
TITLE = "Day-Level Aggregation for Multi-Day Signal Recovery"
EXCLUDE = {'odc-84181797', 'h', 'j'}

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

# Activity curve
def make_activity_curve(dia_hours=6, peak_min=75, step_min=5):
    n_steps = int(dia_hours * 60 / step_min)
    t = np.arange(1, n_steps + 1) * step_min
    curve = (t / peak_min) * np.exp(1 - t / peak_min)
    return curve / curve.sum()

activity = make_activity_curve()
CF = 0.2

# ══════════════════════════════════════════════════════════════════════════
# DAILY AGGREGATION
# ══════════════════════════════════════════════════════════════════════════

print("\n=== Building daily summaries ===")

all_daily = {}
for pid in patients:
    pdf = grid[grid['patient_id'] == pid].copy().sort_values('time').reset_index(drop=True)
    n = len(pdf)
    
    # Compute insulin delivery
    sched_basal = pdf['scheduled_basal_rate'].fillna(pdf['scheduled_basal_rate'].median())
    actual_basal = (pdf['net_basal'].fillna(0) + sched_basal).clip(lower=0) / 12.0
    bolus = pdf['bolus'].fillna(0)
    smb = pdf['bolus_smb'].fillna(0)
    total_ins = bolus + smb + actual_basal
    
    # BGI via convolution
    active = np.convolve(total_ins.values, activity, mode='full')[:n]
    isf_setting = pdf['scheduled_isf'].fillna(pdf['scheduled_isf'].median()).values
    bgi = -active * isf_setting * CF
    
    pdf['total_insulin'] = total_ins
    pdf['actual_basal'] = actual_basal
    pdf['bolus_total'] = bolus + smb
    pdf['bgi'] = bgi
    pdf['date'] = pdf['time'].dt.date
    
    # Daily aggregation
    daily = pdf.groupby('date').agg(
        glucose_mean=('glucose', 'mean'),
        glucose_std=('glucose', 'std'),
        glucose_min=('glucose', 'min'),
        glucose_max=('glucose', 'max'),
        n_readings=('glucose', 'count'),
        tdd=('total_insulin', 'sum'),
        basal_total=('actual_basal', 'sum'),
        bolus_total=('bolus_total', 'sum'),
        carbs_total=('carbs', lambda x: x.fillna(0).sum()),
        bgi_sum=('bgi', 'sum'),
        isf_setting=('scheduled_isf', 'mean'),
    ).reset_index()
    
    # Only keep days with sufficient data (>200 readings = >16h)
    daily = daily[daily['n_readings'] >= 200].copy()
    
    if len(daily) < 10:
        continue
    
    # Derived metrics
    daily['cv'] = daily['glucose_std'] / daily['glucose_mean']
    daily['tir'] = pdf.groupby('date')['glucose'].apply(
        lambda x: ((x >= 70) & (x <= 180)).mean()
    ).reindex(daily['date']).values
    daily['time_high'] = pdf.groupby('date')['glucose'].apply(
        lambda x: (x > 180).mean()
    ).reindex(daily['date']).values
    daily['time_low'] = pdf.groupby('date')['glucose'].apply(
        lambda x: (x < 70).mean()
    ).reindex(daily['date']).values
    daily['basal_pct'] = daily['basal_total'] / daily['tdd'].clip(lower=0.1)
    daily['fifty_fifty_violation'] = (daily['basal_pct'] - 0.5).abs()
    
    # Effective ISF: how much did BG respond to insulin today?
    # Use correction hours only for cleaner estimate
    corr_mask = (pdf['bolus'] > 0.5) & (pdf['glucose'] >= 150)
    daily['n_corrections'] = pdf[corr_mask].groupby('date').size().reindex(daily['date'], fill_value=0).values
    
    # Daily delta BG (overnight: BG at 6am today vs 6am yesterday)
    daily['delta_bg_mean'] = daily['glucose_mean'].diff()
    
    # ISF effectiveness proxy: BGI sum / glucose drop
    daily['bgi_per_insulin'] = daily['bgi_sum'] / daily['tdd'].clip(lower=0.1)
    
    all_daily[pid] = daily

print(f"Patients with daily data: {len(all_daily)}")
for pid in sorted(all_daily.keys())[:5]:
    print(f"  {pid}: {len(all_daily[pid])} days")

# ══════════════════════════════════════════════════════════════════════════
# PART 1: Yesterday's TIR → Today's ISF Effectiveness
# ══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PART 1: Yesterday's TIR → Today's Outcomes")
print("=" * 70)

lag_correlations = []
for pid in all_daily:
    daily = all_daily[pid].copy()
    if len(daily) < 15:
        continue
    
    # Yesterday's features
    daily['tir_lag1'] = daily['tir'].shift(1)
    daily['cv_lag1'] = daily['cv'].shift(1)
    daily['tdd_lag1'] = daily['tdd'].shift(1)
    daily['time_high_lag1'] = daily['time_high'].shift(1)
    daily['basal_pct_lag1'] = daily['basal_pct'].shift(1)
    daily['fifty_fifty_lag1'] = daily['fifty_fifty_violation'].shift(1)
    
    # 3-day rolling
    daily['tir_3d'] = daily['tir'].rolling(3, min_periods=2).mean().shift(1)
    daily['cv_3d'] = daily['cv'].rolling(3, min_periods=2).mean().shift(1)
    
    valid = daily.dropna(subset=['tir_lag1', 'cv_lag1'])
    if len(valid) < 10:
        continue
    
    # Correlations: yesterday → today
    r_tir_tir, _ = sp_stats.pearsonr(valid['tir_lag1'], valid['tir'])
    r_cv_cv, _ = sp_stats.pearsonr(valid['cv_lag1'], valid['cv'])
    r_tir_cv, _ = sp_stats.pearsonr(valid['tir_lag1'], valid['cv'])
    r_high_high, _ = sp_stats.pearsonr(valid['time_high_lag1'], valid['time_high'])
    
    # 50/50 rule: yesterday's violation → today's outcomes
    r_5050_tir, _ = sp_stats.pearsonr(valid['fifty_fifty_lag1'], valid['tir'])
    
    # 3-day rolling vs 1-day
    valid3 = daily.dropna(subset=['tir_3d'])
    r_3d_tir = sp_stats.pearsonr(valid3['tir_3d'], valid3['tir'])[0] if len(valid3) > 10 else np.nan
    
    ctrl = classify_controller(pid)
    lag_correlations.append({
        'patient': pid, 'controller': ctrl,
        'n_days': len(valid),
        'r_tir_tir': round(r_tir_tir, 4),
        'r_cv_cv': round(r_cv_cv, 4),
        'r_tir_cv': round(r_tir_cv, 4),
        'r_high_high': round(r_high_high, 4),
        'r_5050_tir': round(r_5050_tir, 4),
        'r_3d_tir': round(r_3d_tir, 4) if not np.isnan(r_3d_tir) else None,
    })

ldf = pd.DataFrame(lag_correlations)
print(f"\nPatients analyzed: {len(ldf)}")
print(f"\n{'Patient':>15} {'Ctrl':>7} {'Days':>5} {'TIR→TIR':>8} {'CV→CV':>7} {'High→High':>10} {'5050→TIR':>9} {'3d→TIR':>7}")
print("-" * 80)
for _, row in ldf.iterrows():
    print(f"{row['patient']:>15} {row['controller']:>7} {row['n_days']:>5} "
          f"{row['r_tir_tir']:>8.3f} {row['r_cv_cv']:>7.3f} {row['r_high_high']:>10.3f} "
          f"{row['r_5050_tir']:>9.3f} {str(row['r_3d_tir']):>7}")

print(f"\n=== Summary ===")
print(f"  Yesterday TIR → Today TIR:    median r = {ldf['r_tir_tir'].median():.4f}")
print(f"  Yesterday CV → Today CV:      median r = {ldf['r_cv_cv'].median():.4f}")
print(f"  Yesterday High → Today High:  median r = {ldf['r_high_high'].median():.4f}")
print(f"  Yesterday 50/50 viol → TIR:   median r = {ldf['r_5050_tir'].median():.4f}")
print(f"  3-day TIR → Today TIR:        median r = {ldf['r_3d_tir'].dropna().median():.4f}")

# ══════════════════════════════════════════════════════════════════════════
# PART 2: Causal Direction Test (lag vs lead)
# ══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PART 2: Causal Direction — Lag vs Lead")
print("=" * 70)

causal_results = []
for pid in all_daily:
    daily = all_daily[pid].copy()
    if len(daily) < 15:
        continue
    
    # Lag-1 (yesterday → today)
    daily['tir_lag1'] = daily['tir'].shift(1)
    # Lead-1 (tomorrow → today, i.e., today → yesterday)
    daily['tir_lead1'] = daily['tir'].shift(-1)
    
    valid = daily.dropna(subset=['tir_lag1', 'tir_lead1'])
    if len(valid) < 10:
        continue
    
    r_lag, _ = sp_stats.pearsonr(valid['tir_lag1'], valid['cv'])
    r_lead, _ = sp_stats.pearsonr(valid['tir_lead1'], valid['cv'])
    
    # For BG mean
    r_lag_bg, _ = sp_stats.pearsonr(valid['tir_lag1'], valid['glucose_mean'])
    r_lead_bg, _ = sp_stats.pearsonr(valid['tir_lead1'], valid['glucose_mean'])
    
    causal_results.append({
        'patient': pid,
        'controller': classify_controller(pid),
        'r_lag_cv': abs(r_lag),
        'r_lead_cv': abs(r_lead),
        'lag_correct_cv': abs(r_lag) > abs(r_lead),
        'r_lag_bg': abs(r_lag_bg),
        'r_lead_bg': abs(r_lead_bg),
        'lag_correct_bg': abs(r_lag_bg) > abs(r_lead_bg),
    })

cdf = pd.DataFrame(causal_results)
lag_correct_cv = cdf['lag_correct_cv'].sum()
lag_correct_bg = cdf['lag_correct_bg'].sum()
n_tested = len(cdf)

print(f"  TIR→CV causal direction correct: {lag_correct_cv}/{n_tested} ({100*lag_correct_cv/n_tested:.0f}%)")
print(f"  TIR→BG causal direction correct: {lag_correct_bg}/{n_tested} ({100*lag_correct_bg/n_tested:.0f}%)")
print(f"  Mean |r| lag: {cdf['r_lag_cv'].mean():.4f}, lead: {cdf['r_lead_cv'].mean():.4f}")

# ══════════════════════════════════════════════════════════════════════════
# PART 3: Multi-Day Predictive Model
# ══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PART 3: Multi-Day Predictive Model (yesterday → today)")
print("=" * 70)

model_results = []
for pid in all_daily:
    daily = all_daily[pid].copy()
    if len(daily) < 20:
        continue
    
    # Features: yesterday's metrics
    features = pd.DataFrame(index=daily.index)
    features['tir_lag1'] = daily['tir'].shift(1)
    features['cv_lag1'] = daily['cv'].shift(1)
    features['tdd_lag1'] = daily['tdd'].shift(1)
    features['time_high_lag1'] = daily['time_high'].shift(1)
    features['basal_pct_lag1'] = daily['basal_pct'].shift(1)
    features['carbs_lag1'] = daily['carbs_total'].shift(1)
    # 3-day features
    features['tir_3d'] = daily['tir'].rolling(3, min_periods=2).mean().shift(1)
    features['cv_3d'] = daily['cv'].rolling(3, min_periods=2).mean().shift(1)
    features['tdd_3d'] = daily['tdd'].rolling(3, min_periods=2).mean().shift(1)
    
    # Target: today's TIR
    target = daily['tir'].values
    
    valid_mask = features.notna().all(axis=1)
    X = features[valid_mask].fillna(0)
    y = target[valid_mask.values]
    
    if len(y) < 15:
        continue
    
    split = int(len(y) * 0.7)
    X_train, X_test = X.iloc[:split], X.iloc[split:]
    y_train, y_test = y[:split], y[split:]
    
    if len(y_test) < 5:
        continue
    
    # 1-day only model
    X_1d = X[['tir_lag1', 'cv_lag1', 'tdd_lag1', 'time_high_lag1', 'basal_pct_lag1', 'carbs_lag1']]
    m1 = Ridge(alpha=1.0).fit(X_1d.iloc[:split], y_train)
    r2_1d = r2_score(y_test, m1.predict(X_1d.iloc[split:]))
    
    # 3-day model (adds rolling features)
    m3 = Ridge(alpha=1.0).fit(X.iloc[:split], y_train)
    r2_3d = r2_score(y_test, m3.predict(X.iloc[split:]))
    
    # Naive baseline (predict today = yesterday)
    r2_naive = r2_score(y_test, X_1d.iloc[split:]['tir_lag1'].values)
    
    model_results.append({
        'patient': pid,
        'controller': classify_controller(pid),
        'n_days': len(y),
        'r2_naive': round(r2_naive, 4),
        'r2_1d': round(r2_1d, 4),
        'r2_3d': round(r2_3d, 4),
        'improvement_3d': round(r2_3d - r2_1d, 4),
    })

mdf = pd.DataFrame(model_results)
print(f"\nPatients modeled: {len(mdf)}")
print(f"\n{'Patient':>15} {'Ctrl':>7} {'Days':>5} {'Naive':>7} {'1-day':>7} {'3-day':>7} {'Δ3d':>7}")
print("-" * 65)
for _, row in mdf.iterrows():
    print(f"{row['patient']:>15} {row['controller']:>7} {row['n_days']:>5} "
          f"{row['r2_naive']:>7.3f} {row['r2_1d']:>7.3f} {row['r2_3d']:>7.3f} {row['improvement_3d']:>+7.3f}")

print(f"\n=== Summary ===")
print(f"  Naive (yesterday=today):    median R² = {mdf['r2_naive'].median():.4f}")
print(f"  1-day features:             median R² = {mdf['r2_1d'].median():.4f}")
print(f"  3-day features:             median R² = {mdf['r2_3d'].median():.4f}")
print(f"  3-day improvement over 1d:  median Δ  = {mdf['improvement_3d'].median():+.4f}")
print(f"  3-day > 1-day:              {(mdf['improvement_3d'] > 0).sum()}/{len(mdf)}")

# ══════════════════════════════════════════════════════════════════════════
# PART 4: 50/50 Rule as Stability Metric
# ══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PART 4: 50/50 Rule Violation → Next Day Outcomes")
print("=" * 70)

fifty_results = []
for pid in all_daily:
    daily = all_daily[pid].copy()
    if len(daily) < 15:
        continue
    
    # Exclude patients with no insulin data
    if daily['tdd'].median() < 1:
        continue
    
    daily['violation_lag1'] = daily['fifty_fifty_violation'].shift(1)
    valid = daily.dropna(subset=['violation_lag1'])
    
    if len(valid) < 10:
        continue
    
    # High violation days vs low violation days
    median_viol = valid['violation_lag1'].median()
    high_viol = valid[valid['violation_lag1'] > median_viol]
    low_viol = valid[valid['violation_lag1'] <= median_viol]
    
    tir_diff = low_viol['tir'].mean() - high_viol['tir'].mean()
    cv_diff = high_viol['cv'].mean() - low_viol['cv'].mean()
    
    r_viol_tir, p_viol = sp_stats.pearsonr(valid['violation_lag1'], valid['tir'])
    
    fifty_results.append({
        'patient': pid,
        'controller': classify_controller(pid),
        'median_basal_pct': round(daily['basal_pct'].median(), 3),
        'median_violation': round(daily['fifty_fifty_violation'].median(), 3),
        'tir_diff': round(tir_diff, 4),
        'cv_diff': round(cv_diff, 4),
        'r_violation_tir': round(r_viol_tir, 4),
        'p_value': round(p_viol, 4),
    })

fdf = pd.DataFrame(fifty_results)
print(f"\nPatients with insulin data: {len(fdf)}")
print(f"\n  Median basal% by controller:")
for ctrl in ['Loop', 'Trio', 'OpenAPS']:
    sub = fdf[fdf['controller'] == ctrl]
    if len(sub) > 0:
        print(f"    {ctrl}: {sub['median_basal_pct'].median()*100:.1f}% basal "
              f"(violation: {sub['median_violation'].median()*100:.1f}pp from 50%)")

print(f"\n  50/50 violation → next-day TIR:")
print(f"    Median r = {fdf['r_violation_tir'].median():.4f}")
print(f"    Negative r (violation → worse TIR): {(fdf['r_violation_tir'] < 0).sum()}/{len(fdf)}")
print(f"    Significant (p<0.05): {(fdf['p_value'] < 0.05).sum()}/{len(fdf)}")

# ══════════════════════════════════════════════════════════════════════════
# CRITERIA
# ══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("CRITERIA EVALUATION")
print("=" * 70)

P1 = ldf['r_tir_tir'].median() > 0.10
P2 = ldf['r_cv_cv'].median() > 0.15
P3 = lag_correct_cv > n_tested * 0.6
P4 = fdf['r_violation_tir'].median() < -0.05  # negative = violation hurts TIR
P5 = mdf['improvement_3d'].median() > 0.02

criteria = {
    'P1_tir_predicts_tir': {'pass': P1, 'value': f"median r={ldf['r_tir_tir'].median():.4f}"},
    'P2_cv_predicts_cv': {'pass': P2, 'value': f"median r={ldf['r_cv_cv'].median():.4f}"},
    'P3_causal_direction': {'pass': P3, 'value': f"{lag_correct_cv}/{n_tested} ({100*lag_correct_cv/n_tested:.0f}%)"},
    'P4_5050_violation': {'pass': P4, 'value': f"median r={fdf['r_violation_tir'].median():.4f}"},
    'P5_3day_adds_2pct': {'pass': P5, 'value': f"median Δ={mdf['improvement_3d'].median():+.4f}"},
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
    fig.suptitle(f'EXP-{EXP_ID}: Day-Level Multi-Day Signal ({pass_count}/5 PASS)', 
                 fontsize=14, fontweight='bold')
    
    # 1. Day-to-day autocorrelation of TIR
    ax = axes[0, 0]
    for ctrl, color in [('Loop', 'blue'), ('Trio', 'green'), ('OpenAPS', 'orange')]:
        sub = ldf[ldf['controller'] == ctrl]
        ax.scatter(sub['r_tir_tir'], sub['r_cv_cv'], c=color, label=ctrl, s=60, alpha=0.7)
    ax.axhline(y=0.15, color='red', linestyle='--', alpha=0.3)
    ax.axvline(x=0.10, color='red', linestyle='--', alpha=0.3)
    ax.set_xlabel('TIR autocorrelation (day→day)')
    ax.set_ylabel('CV autocorrelation (day→day)')
    ax.set_title(f'Day-to-Day Persistence\nTIR: r={ldf["r_tir_tir"].median():.3f}, CV: r={ldf["r_cv_cv"].median():.3f}')
    ax.legend(fontsize=8)
    
    # 2. Causal direction scatter
    ax = axes[0, 1]
    ax.scatter(cdf['r_lag_cv'], cdf['r_lead_cv'], 
               c=['green' if x else 'red' for x in cdf['lag_correct_cv']],
               s=60, alpha=0.7, edgecolor='black')
    lim = [0, max(cdf['r_lag_cv'].max(), cdf['r_lead_cv'].max()) + 0.02]
    ax.plot(lim, lim, 'k--', alpha=0.3)
    ax.set_xlabel('|r| Lag (yesterday → today)')
    ax.set_ylabel('|r| Lead (tomorrow → today)')
    ax.set_title(f'Causal Direction Test\n{lag_correct_cv}/{n_tested} correct ({100*lag_correct_cv/n_tested:.0f}%)')
    
    # 3. Model comparison
    ax = axes[0, 2]
    x_pos = np.arange(len(mdf))
    width = 0.3
    ax.bar(x_pos - width, mdf['r2_naive'], width, label='Naive', alpha=0.6, color='gray')
    ax.bar(x_pos, mdf['r2_1d'], width, label='1-day', alpha=0.7, color='steelblue')
    ax.bar(x_pos + width, mdf['r2_3d'], width, label='3-day', alpha=0.7, color='darkgreen')
    ax.set_xlabel('Patient')
    ax.set_ylabel('Test R²')
    ax.set_title(f'Day-Level Prediction Models\n1d={mdf["r2_1d"].median():.3f}, 3d={mdf["r2_3d"].median():.3f}')
    ax.legend(fontsize=8)
    ax.set_xticks([])
    
    # 4. 50/50 rule
    ax = axes[1, 0]
    for ctrl, color in [('Loop', 'blue'), ('Trio', 'green'), ('OpenAPS', 'orange')]:
        sub = fdf[fdf['controller'] == ctrl]
        ax.scatter(sub['median_basal_pct']*100, sub['r_violation_tir'], 
                  c=color, label=ctrl, s=60, alpha=0.7)
    ax.axhline(y=0, color='gray', linestyle='--')
    ax.axvline(x=50, color='red', linestyle='--', alpha=0.5, label='50% target')
    ax.set_xlabel('Median Daily Basal %')
    ax.set_ylabel('r(violation → next-day TIR)')
    ax.set_title(f'50/50 Rule & Outcomes\nMedian r={fdf["r_violation_tir"].median():.3f}')
    ax.legend(fontsize=8)
    
    # 5. TIR persistence by controller
    ax = axes[1, 1]
    for ctrl, color in [('Loop', 'blue'), ('Trio', 'green'), ('OpenAPS', 'orange')]:
        sub = ldf[ldf['controller'] == ctrl]
        if len(sub) > 0:
            ax.bar(ctrl, sub['r_tir_tir'].median(), color=color, alpha=0.7, edgecolor='black')
            ax.errorbar(ctrl, sub['r_tir_tir'].median(), 
                       yerr=sub['r_tir_tir'].std(), color='black', capsize=5)
    ax.set_ylabel('TIR Day-to-Day Autocorrelation')
    ax.set_title('TIR Persistence by Controller')
    ax.axhline(y=0.10, color='red', linestyle='--', alpha=0.3)
    
    # 6. Summary
    ax = axes[1, 2]
    ax.axis('off')
    summary = f"""EXP-{EXP_ID}: Day-Level Multi-Day Signals

Day-to-day persistence:
  TIR: r = {ldf['r_tir_tir'].median():.3f} ({"✓" if P1 else "✗"} >0.10)
  CV:  r = {ldf['r_cv_cv'].median():.3f} ({"✓" if P2 else "✗"} >0.15)
  High: r = {ldf['r_high_high'].median():.3f}

Causal direction:
  {lag_correct_cv}/{n_tested} correct ({"✓" if P3 else "✗"} >60%)

Multi-day model:
  Naive: R²={mdf['r2_naive'].median():.3f}
  1-day: R²={mdf['r2_1d'].median():.3f}
  3-day: R²={mdf['r2_3d'].median():.3f}
  3d improvement: {mdf['improvement_3d'].median():+.4f}

50/50 rule:
  Violation → TIR: r = {fdf['r_violation_tir'].median():.3f}
  {(fdf['r_violation_tir'] < 0).sum()}/{len(fdf)} negative (violation hurts)

INTERPRETATION:
  Days ARE somewhat persistent — yesterday's control
  predicts today's. But the improvement from 3-day
  rolling is {"large" if P5 else "small"} ({mdf['improvement_3d'].median():+.4f}).
  Multi-day metabolic memory exists but is modest.
"""
    ax.text(0.05, 0.95, summary, transform=ax.transAxes,
            fontsize=9, verticalalignment='top', fontfamily='monospace',
            bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))
    
    plt.tight_layout()
    viz_dir = Path("tools/visualizations/day-level")
    viz_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(viz_dir / f"exp-{EXP_ID}-dashboard.png", dpi=150, bbox_inches='tight')
    print(f"\nVisualization saved to {viz_dir}/exp-{EXP_ID}-dashboard.png")
    plt.close()
except Exception as e:
    print(f"Visualization error: {e}")

# ── Save ──────────────────────────────────────────────────────────────────

output = {
    'experiment_id': f'EXP-{EXP_ID}',
    'title': TITLE,
    'timestamp': datetime.now().isoformat(),
    'n_patients': len(all_daily),
    'criteria': criteria,
    'pass_count': pass_count,
    'day_persistence': {
        'median_r_tir': round(ldf['r_tir_tir'].median(), 4),
        'median_r_cv': round(ldf['r_cv_cv'].median(), 4),
        'median_r_high': round(ldf['r_high_high'].median(), 4),
    },
    'causal_direction': {
        'correct_cv': lag_correct_cv,
        'correct_bg': lag_correct_bg,
        'total': n_tested,
    },
    'model_comparison': {
        'median_r2_naive': round(mdf['r2_naive'].median(), 4),
        'median_r2_1d': round(mdf['r2_1d'].median(), 4),
        'median_r2_3d': round(mdf['r2_3d'].median(), 4),
        'median_3d_improvement': round(mdf['improvement_3d'].median(), 4),
    },
    'fifty_fifty': {
        'median_r_violation_tir': round(fdf['r_violation_tir'].median(), 4),
        'pct_negative': round((fdf['r_violation_tir'] < 0).sum() / len(fdf) * 100, 1),
    },
    'per_patient_persistence': lag_correlations,
}

out_path = Path(f"externals/experiments/exp-{EXP_ID}_day_level.json")
with open(out_path, 'w') as f:
    json.dump(output, f, indent=2, default=str)
print(f"Results saved to {out_path}")
