#!/usr/bin/env python3
"""
EXP-2809: Sensor-Gap Controller Effect Estimation
==================================================

Rationale:
  EXP-2808 showed sensor gaps are the ONE truly exogenous event in AID data.
  During gaps, the controller is blind (no CGM input) and runs on defaults.
  This creates a quasi-natural-experiment: same patient, same physiology,
  but controller effectiveness is reduced.
  
  By comparing glucose behavior during controller-blind periods vs normal,
  we can estimate the CAUSAL effect of controller intervention:
  - How much does the controller reduce mean BG?
  - How much does the controller reduce variability?
  - Does the effect differ by controller type?
  - Can we estimate true uncontrolled EGP from the drift during gaps?
  
  This also helps validate ISF: if the controller is blind and BG rises,
  the rate of rise reveals unopposed glucose production that the controller
  normally counteracts.

Success criteria:
  P1: Controller effect on mean BG: post-gap BG > pre-gap BG (proven)
  P2: Controller effect on variability: post-gap std > normal std
  P3: BG drift rate during gap estimates EGP (5-15 mg/dL/hr range)
  P4: Controller type differences in gap recovery speed
  P5: Gap-derived ISF estimate correlates with extracted ISF (r > 0.3)
"""

import json
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

warnings.filterwarnings('ignore')

EXP_ID = 2809
TITLE = "Sensor-Gap Controller Effect"
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

def make_activity_curve(dia_hours=6, peak_min=75, step_min=5):
    n_steps = int(dia_hours * 60 / step_min)
    t = np.arange(1, n_steps + 1) * step_min
    curve = (t / peak_min) * np.exp(1 - t / peak_min)
    return curve / curve.sum()

activity = make_activity_curve()

print(f"Patients: {len(patients)}")
print("\n" + "=" * 70)
print("PART 1: Sensor Gap Detection & BG Drift Analysis")
print("=" * 70)

# ══════════════════════════════════════════════════════════════════════════
# DETECT SENSOR GAPS AND MEASURE DRIFT
# ══════════════════════════════════════════════════════════════════════════

gap_data = []
per_patient_gaps = {}

for pid in patients:
    pdf = grid[grid['patient_id'] == pid].reset_index(drop=True)
    n = len(pdf)
    ctrl = classify_controller(pid)
    gluc = pdf['glucose'].values
    
    # Detect NaN gaps ≥30min
    nan_mask = np.isnan(gluc)
    in_gap = False
    gap_start = 0
    patient_gaps = []
    
    for i in range(n):
        if nan_mask[i] and not in_gap:
            gap_start = i
            in_gap = True
        elif not nan_mask[i] and in_gap:
            gap_len = i - gap_start
            if gap_len >= 6:  # ≥30 min
                # Need 2h context before and after
                if gap_start >= 24 and i + 24 < n:
                    pre = gluc[gap_start-24:gap_start]
                    post = gluc[i:i+24]
                    
                    if np.isnan(pre).sum() < 4 and np.isnan(post).sum() < 4:
                        # BG at gap boundaries
                        bg_entering = np.nanmean(pre[-6:])  # last 30min before gap
                        bg_exiting = np.nanmean(post[:6])   # first 30min after gap
                        
                        # Drift during gap
                        drift = bg_exiting - bg_entering
                        drift_per_hour = drift / (gap_len * 5 / 60)
                        
                        # Normal BG stats for this patient (non-gap)
                        normal_bg_before = np.nanmean(pre)
                        normal_std_before = np.nanstd(pre)
                        
                        # Post-gap recovery: how fast does BG normalize?
                        bg_30min_after = np.nanmean(post[:6])
                        bg_1h_after = np.nanmean(post[:12])
                        bg_2h_after = np.nanmean(post[-6:])
                        
                        recovery_1h = bg_30min_after - bg_1h_after  # should be positive (coming down)
                        recovery_2h = bg_30min_after - bg_2h_after
                        
                        patient_gaps.append({
                            'patient': pid, 'controller': ctrl,
                            'gap_start': gap_start, 'gap_end': i,
                            'gap_duration_min': gap_len * 5,
                            'bg_entering': bg_entering,
                            'bg_exiting': bg_exiting,
                            'drift': drift,
                            'drift_per_hour': drift_per_hour,
                            'pre_mean': normal_bg_before,
                            'post_mean': np.nanmean(post),
                            'pre_std': normal_std_before,
                            'post_std': np.nanstd(post),
                            'recovery_1h': recovery_1h,
                            'recovery_2h': recovery_2h,
                        })
            in_gap = False
    
    if patient_gaps:
        per_patient_gaps[pid] = patient_gaps
        gap_data.extend(patient_gaps)

gdf = pd.DataFrame(gap_data)
print(f"\nTotal sensor gaps with context: {len(gdf)} across {len(per_patient_gaps)} patients")
print(f"Median gap duration: {gdf['gap_duration_min'].median():.0f} min")

# ══════════════════════════════════════════════════════════════════════════
# PART 2: BG Drift During Gaps (EGP Estimation)
# ══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PART 2: BG Drift During Sensor Gaps (Unopposed EGP)")
print("=" * 70)

# During sensor gaps, the controller runs on defaults (or suspends)
# BG drift = EGP - residual_insulin_effect
# If gap is long enough, residual insulin has largely dissipated

# Stratify by gap duration
for min_dur, max_dur, label in [(30, 60, '30-60min'), (60, 120, '1-2h'), (120, 300, '2-5h'), (300, 1500, '>5h')]:
    sub = gdf[(gdf['gap_duration_min'] >= min_dur) & (gdf['gap_duration_min'] < max_dur)]
    if len(sub) > 5:
        drift = sub['drift_per_hour'].values
        drift_clean = drift[(drift > -50) & (drift < 50)]
        print(f"  {label}: n={len(sub)}, median drift={np.median(drift_clean):+.1f} mg/dL/hr, "
              f"IQR=[{np.percentile(drift_clean, 25):.1f}, {np.percentile(drift_clean, 75):.1f}]")

# Longer gaps should show more positive drift (insulin wears off, EGP dominates)
long_gaps = gdf[gdf['gap_duration_min'] >= 120]
short_gaps = gdf[(gdf['gap_duration_min'] >= 30) & (gdf['gap_duration_min'] < 120)]

if len(long_gaps) > 10 and len(short_gaps) > 10:
    long_drift = long_gaps['drift_per_hour'].values
    short_drift = short_gaps['drift_per_hour'].values
    long_drift = long_drift[(long_drift > -50) & (long_drift < 50)]
    short_drift = short_drift[(short_drift > -50) & (short_drift < 50)]
    t_dur, p_dur = sp_stats.mannwhitneyu(long_drift, short_drift, alternative='greater')
    print(f"\n  Long (≥2h) vs short (<2h) gap drift:")
    print(f"    Long median:  {np.median(long_drift):+.1f} mg/dL/hr")
    print(f"    Short median: {np.median(short_drift):+.1f} mg/dL/hr")
    print(f"    Mann-Whitney (long>short): U={t_dur:.0f}, p={p_dur:.4f}")

# Best EGP estimate: from longest gaps where insulin has worn off
best_egp = gdf[gdf['gap_duration_min'] >= 180]['drift_per_hour']
best_egp_clean = best_egp[(best_egp > -30) & (best_egp < 30)]
if len(best_egp_clean) > 5:
    egp_estimate = np.median(best_egp_clean)
    print(f"\n  Best EGP estimate (gaps ≥3h): {egp_estimate:+.1f} mg/dL/hr")
    print(f"  N events: {len(best_egp_clean)}")
    egp_in_range = 5 <= egp_estimate <= 15
else:
    egp_estimate = np.nan
    egp_in_range = False

# ══════════════════════════════════════════════════════════════════════════
# PART 3: Controller Effect by Type
# ══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PART 3: Controller Type Differences in Gap Behavior")
print("=" * 70)

for ctrl in ['Loop', 'Trio', 'OpenAPS']:
    sub = gdf[gdf['controller'] == ctrl]
    if len(sub) > 10:
        drift = sub['drift_per_hour'].values
        drift_clean = drift[(drift > -50) & (drift < 50)]
        recovery = sub['recovery_2h'].values
        recovery_clean = recovery[~np.isnan(recovery) & (np.abs(recovery) < 100)]
        
        print(f"\n  {ctrl} (n={len(sub)} gaps):")
        print(f"    Median drift:     {np.median(drift_clean):+.1f} mg/dL/hr")
        print(f"    BG rise (gap):    {sub['drift'].median():+.1f} mg/dL")
        print(f"    Post-gap recovery: {np.median(recovery_clean):+.1f} mg/dL in 2h")
        print(f"    Pre-gap mean BG:  {sub['pre_mean'].median():.1f}")
        print(f"    Post-gap mean BG: {sub['post_mean'].median():.1f}")

# ══════════════════════════════════════════════════════════════════════════
# PART 4: Controller Causal Effect Estimation
# ══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PART 4: Controller Causal Effect (Gap vs Non-Gap)")
print("=" * 70)

# Compare per-patient: mean BG during non-gap periods vs immediately post-gap
controller_effects = []
for pid, gaps in per_patient_gaps.items():
    ctrl = classify_controller(pid)
    pdf = grid[grid['patient_id'] == pid]
    
    # Overall mean BG for this patient
    overall_mean = pdf['glucose'].mean()
    overall_std = pdf['glucose'].std()
    
    # Post-gap mean (first 2h after each gap)
    post_gap_means = [g['post_mean'] for g in gaps]
    post_gap_mean = np.mean(post_gap_means)
    
    # Controller effect = post_gap_mean - overall_mean
    # Positive = gap causes BG to be higher = controller was keeping it lower
    effect = post_gap_mean - overall_mean
    
    controller_effects.append({
        'patient': pid, 'controller': ctrl,
        'n_gaps': len(gaps),
        'overall_mean': overall_mean,
        'post_gap_mean': post_gap_mean,
        'controller_effect': effect,
    })

cedf = pd.DataFrame(controller_effects)
print(f"\n  Controller causal effect on mean BG:")
print(f"    Median effect: {cedf['controller_effect'].median():+.1f} mg/dL")
print(f"    (Positive = controller keeps BG lower by this amount)")
print(f"    Positive effect: {(cedf['controller_effect'] > 0).sum()}/{len(cedf)}")

for ctrl in ['Loop', 'Trio', 'OpenAPS']:
    sub = cedf[cedf['controller'] == ctrl]
    if len(sub) > 0:
        print(f"    {ctrl}: {sub['controller_effect'].median():+.1f} mg/dL")

t_effect, p_effect = sp_stats.ttest_1samp(cedf['controller_effect'].dropna(), 0)
print(f"    t-test (effect > 0): t={t_effect:.2f}, p={p_effect:.4f}")

# ══════════════════════════════════════════════════════════════════════════
# PART 5: Gap-Derived ISF vs Extracted ISF
# ══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PART 5: Gap-Derived vs Extracted ISF Correlation")
print("=" * 70)

# Load EXP-2805 results for comparison
try:
    with open("externals/experiments/exp-2805_category_settings.json") as f:
        exp2805 = json.load(f)
    isf_extracted = {k: v['isf_optimal'] for k, v in exp2805.get('isf_results', {}).items()}
except:
    isf_extracted = {}

# Gap-derived ISF: the controller effect / typical insulin delivered during gap period
# This is very rough: ISF ≈ BG_rise_per_hour / insulin_reduction_per_hour
# Since we don't know exact insulin during gaps, use controller_effect as proxy

if isf_extracted:
    both = [(pid, cedf.loc[cedf['patient']==pid, 'controller_effect'].values[0], isf_extracted.get(pid))
            for pid in isf_extracted.keys()
            if pid in cedf['patient'].values and isf_extracted.get(pid)]
    
    if len(both) > 5:
        effects = [b[1] for b in both]
        isfs = [b[2] for b in both]
        r_isf, p_isf = sp_stats.pearsonr(effects, isfs)
        print(f"  Controller effect vs extracted ISF: r={r_isf:.3f}, p={p_isf:.4f}")
        print(f"  (Positive r = more effect → higher ISF = consistent)")
        isf_corr = r_isf
    else:
        isf_corr = 0
        print("  Insufficient overlap")
else:
    isf_corr = 0
    print("  No EXP-2805 ISF data available")

# ══════════════════════════════════════════════════════════════════════════
# CRITERIA
# ══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("CRITERIA EVALUATION")
print("=" * 70)

P1 = cedf['controller_effect'].median() > 0
p1_val = f"Median effect = {cedf['controller_effect'].median():+.1f} mg/dL"

P2 = gdf['post_std'].median() > gdf['pre_std'].median()
p2_val = f"Post-gap std={gdf['post_std'].median():.1f} vs pre={gdf['pre_std'].median():.1f}"

P3 = egp_in_range
p3_val = f"EGP estimate = {egp_estimate:+.1f} mg/dL/hr (expect 5-15)" if not np.isnan(egp_estimate) else "Insufficient data"

P4_data = []
for ctrl in ['Loop', 'Trio', 'OpenAPS']:
    sub = cedf[cedf['controller'] == ctrl]
    if len(sub) > 2:
        P4_data.append(sub['controller_effect'].median())
P4 = len(P4_data) >= 2 and max(P4_data) - min(P4_data) > 3
p4_val = f"Range: {min(P4_data):.1f} to {max(P4_data):.1f}" if P4_data else "Insufficient"

P5 = abs(isf_corr) > 0.3
p5_val = f"r={isf_corr:.3f}" if isf_corr != 0 else "No data"

criteria = {
    'P1_controller_reduces_bg': {'pass': P1, 'value': p1_val},
    'P2_gap_volatility_higher': {'pass': P2, 'value': p2_val},
    'P3_egp_in_range': {'pass': P3, 'value': p3_val},
    'P4_controller_differences': {'pass': P4, 'value': p4_val},
    'P5_isf_correlation': {'pass': P5, 'value': p5_val},
}

pass_count = sum(1 for c in criteria.values() if c['pass'])
for name, c in criteria.items():
    status = "PASS ✓" if c['pass'] else "FAIL ✗"
    print(f"  {name}: {status} — {c['value']}")
print(f"\nOverall: {pass_count}/5 criteria passed")

# ── Save ──────────────────────────────────────────────────────────────────

output = {
    'experiment_id': f'EXP-{EXP_ID}',
    'title': TITLE,
    'timestamp': datetime.now().isoformat(),
    'n_gaps': len(gdf),
    'n_patients': len(per_patient_gaps),
    'criteria': criteria,
    'pass_count': pass_count,
    'controller_effects': controller_effects,
    'egp_estimate': float(egp_estimate) if not np.isnan(egp_estimate) else None,
}

out_path = Path(f"externals/experiments/exp-{EXP_ID}_sensor_gap_effect.json")
with open(out_path, 'w') as f:
    json.dump(output, f, indent=2, default=str)
print(f"\nResults saved to {out_path}")
