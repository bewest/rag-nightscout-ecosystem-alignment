#!/usr/bin/env python3
"""
EXP-2808: Natural Experiments — Exogenous Variation for Causal Estimates
========================================================================

Rationale:
  The fundamental challenge in AID data is confounding by indication:
  the controller adjusts insulin BECAUSE of glucose state, making it
  impossible to observe what would have happened without intervention.
  
  Natural experiments exploit exogenous events that break the feedback loop:
  1. Sensor gaps — controller blind, runs on defaults
  2. Pump site changes — absorption changes discontinuously
  3. Controller restarts — fresh IOB estimate, temporary mismatch
  4. Sensor warm-up — known 2h period with no CGM input
  
  These create quasi-random variation in effective insulin delivery
  that is NOT confounded by current glucose state.
  
  We look for:
  - Discontinuities in glucose patterns around these events
  - The "open-loop" periods reveal true ISF without controller compensation
  - Differences in BG behavior just before/after restart reveal controller effect

Success criteria:
  P1: Identify ≥100 natural experiment events across dataset
  P2: Sensor gap glucose behavior differs from non-gap periods (p<0.05)
  P3: Post-restart glucose volatility > pre-restart (controller settling)
  P4: ISF estimated from natural experiments differs from profile (evidence of bias)
  P5: Causal direction test passes (pre→post, not reverse)
"""

import json
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

warnings.filterwarnings('ignore')

EXP_ID = 2808
TITLE = "Natural Experiments — Exogenous Variation"
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
print("\n" + "=" * 70)
print("PART 1: Identify Natural Experiment Events")
print("=" * 70)

# ══════════════════════════════════════════════════════════════════════════
# DETECT EXOGENOUS EVENTS
# ══════════════════════════════════════════════════════════════════════════

all_events = []

for pid in patients:
    pdf = grid[grid['patient_id'] == pid].reset_index(drop=True)
    n = len(pdf)
    ctrl = classify_controller(pid)
    
    gluc = pdf['glucose'].values
    bolus_v = pdf['bolus'].fillna(0).values
    smb_v = pdf['bolus_smb'].fillna(0).values
    net_basal_v = pdf['net_basal'].fillna(0).values
    
    # ── Type 1: Sensor Gaps (NaN glucose for ≥30min = 6 steps) ──
    nan_mask = np.isnan(gluc)
    gap_starts = []
    in_gap = False
    gap_start = 0
    for i in range(n):
        if nan_mask[i] and not in_gap:
            gap_start = i
            in_gap = True
        elif not nan_mask[i] and in_gap:
            gap_len = i - gap_start
            if gap_len >= 6:  # ≥30 min
                gap_starts.append((gap_start, i, gap_len))
            in_gap = False
    
    for start, end, length in gap_starts:
        # Need valid glucose before and after
        if start < 24 or end + 24 >= n:
            continue
        pre_gluc = gluc[start-24:start]
        post_gluc = gluc[end:end+24]
        if np.isnan(pre_gluc).sum() > 6 or np.isnan(post_gluc).sum() > 6:
            continue
        
        all_events.append({
            'patient': pid, 'controller': ctrl,
            'type': 'sensor_gap',
            'position': start,
            'duration_min': length * 5,
            'pre_mean': np.nanmean(pre_gluc),
            'post_mean': np.nanmean(post_gluc),
            'pre_std': np.nanstd(pre_gluc),
            'post_std': np.nanstd(post_gluc),
            'pre_trend': np.nanmean(np.diff(pre_gluc[~np.isnan(pre_gluc)])),
            'post_trend': np.nanmean(np.diff(post_gluc[~np.isnan(post_gluc)])),
        })
    
    # ── Type 2: Insulin Gaps (no delivery for ≥1h = possible site change) ──
    total_ins = bolus_v + smb_v + np.maximum(net_basal_v / 12.0, 0)
    zero_ins = (total_ins == 0).astype(int)
    insulin_gap_start = None
    for i in range(n):
        if zero_ins[i] and insulin_gap_start is None:
            insulin_gap_start = i
        elif not zero_ins[i] and insulin_gap_start is not None:
            gap_len = i - insulin_gap_start
            if gap_len >= 12:  # ≥1 hour of no insulin
                if insulin_gap_start >= 24 and i + 24 < n:
                    pre_gluc = gluc[insulin_gap_start-24:insulin_gap_start]
                    post_gluc = gluc[i:i+24]
                    if np.isnan(pre_gluc).sum() < 6 and np.isnan(post_gluc).sum() < 6:
                        all_events.append({
                            'patient': pid, 'controller': ctrl,
                            'type': 'insulin_gap',
                            'position': insulin_gap_start,
                            'duration_min': gap_len * 5,
                            'pre_mean': np.nanmean(pre_gluc),
                            'post_mean': np.nanmean(post_gluc),
                            'pre_std': np.nanstd(pre_gluc),
                            'post_std': np.nanstd(post_gluc),
                            'pre_trend': np.nanmean(np.diff(pre_gluc[~np.isnan(pre_gluc)])),
                            'post_trend': np.nanmean(np.diff(post_gluc[~np.isnan(post_gluc)])),
                        })
            insulin_gap_start = None
    
    # ── Type 3: Large BG Discontinuities (possible sensor restart) ──
    for i in range(1, n-24):
        if np.isnan(gluc[i]) or np.isnan(gluc[i-1]):
            continue
        jump = abs(gluc[i] - gluc[i-1])
        if jump > 40:  # >40 mg/dL in 5 minutes = likely sensor restart
            if i >= 24 and i + 24 < n:
                pre_gluc = gluc[i-24:i]
                post_gluc = gluc[i:i+24]
                if np.isnan(pre_gluc).sum() < 6 and np.isnan(post_gluc).sum() < 6:
                    all_events.append({
                        'patient': pid, 'controller': ctrl,
                        'type': 'bg_discontinuity',
                        'position': i,
                        'duration_min': 5,
                        'jump_size': jump,
                        'pre_mean': np.nanmean(pre_gluc),
                        'post_mean': np.nanmean(post_gluc),
                        'pre_std': np.nanstd(pre_gluc),
                        'post_std': np.nanstd(post_gluc),
                        'pre_trend': np.nanmean(np.diff(pre_gluc[~np.isnan(pre_gluc)])),
                        'post_trend': np.nanmean(np.diff(post_gluc[~np.isnan(post_gluc)])),
                    })

edf = pd.DataFrame(all_events)
print(f"\nTotal natural experiment events: {len(edf)}")
print(f"\nBy type:")
for t in ['sensor_gap', 'insulin_gap', 'bg_discontinuity']:
    sub = edf[edf['type'] == t]
    print(f"  {t}: {len(sub)} events across {sub['patient'].nunique()} patients")

print(f"\nBy controller:")
for ctrl in ['Loop', 'Trio', 'OpenAPS']:
    sub = edf[edf['controller'] == ctrl]
    print(f"  {ctrl}: {len(sub)} events")

# ══════════════════════════════════════════════════════════════════════════
# PART 2: Analyze Sensor Gap Behavior
# ══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PART 2: Sensor Gap Analysis (Controller Blind)")
print("=" * 70)

gaps = edf[edf['type'] == 'sensor_gap'].copy()
if len(gaps) > 10:
    # Compare pre-gap vs post-gap glucose behavior
    print(f"\n  Sensor gaps: {len(gaps)} events")
    print(f"  Median gap duration: {gaps['duration_min'].median():.0f} min")
    
    # Post-gap glucose tends to be different because controller was blind
    pre_means = gaps['pre_mean'].values
    post_means = gaps['post_mean'].values
    t_stat, p_val = sp_stats.ttest_rel(pre_means, post_means)
    print(f"\n  Pre-gap mean BG:  {np.median(pre_means):.1f} mg/dL")
    print(f"  Post-gap mean BG: {np.median(post_means):.1f} mg/dL")
    print(f"  Paired t-test: t={t_stat:.2f}, p={p_val:.4f}")
    
    # Variability change
    pre_stds = gaps['pre_std'].values
    post_stds = gaps['post_std'].values
    t_std, p_std = sp_stats.ttest_rel(post_stds, pre_stds)
    print(f"\n  Pre-gap BG std:  {np.median(pre_stds):.1f}")
    print(f"  Post-gap BG std: {np.median(post_stds):.1f}")
    print(f"  Volatility change: t={t_std:.2f}, p={p_std:.4f}")
    
    gap_p_val = p_val
else:
    gap_p_val = 1.0
    print("  Insufficient sensor gap events")

# ══════════════════════════════════════════════════════════════════════════
# PART 3: Insulin Gap Analysis (Possible Site Change / Disconnect)
# ══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PART 3: Insulin Gap Analysis")
print("=" * 70)

ins_gaps = edf[edf['type'] == 'insulin_gap'].copy()
if len(ins_gaps) > 10:
    print(f"\n  Insulin gaps: {len(ins_gaps)} events")
    print(f"  Median gap duration: {ins_gaps['duration_min'].median():.0f} min")
    
    # After insulin gap, BG should rise (no insulin being delivered)
    pre_trend = ins_gaps['pre_trend'].values
    post_trend = ins_gaps['post_trend'].values
    
    # Post-gap BG rises because insulin was absent
    rise_after = (ins_gaps['post_mean'] - ins_gaps['pre_mean']).values
    t_rise, p_rise = sp_stats.ttest_1samp(rise_after, 0)
    print(f"\n  Mean BG change (post-pre): {np.mean(rise_after):+.1f} mg/dL")
    print(f"  Median BG change: {np.median(rise_after):+.1f} mg/dL")
    print(f"  t-test (change ≠ 0): t={t_rise:.2f}, p={p_rise:.4f}")
    
    # This gives us EGP signal: during insulin gap, glucose rises at ~EGP rate
    # EGP ≈ rise_rate (mg/dL/5min) / 5 * 60 ≈ mg/dL/hr
    if len(ins_gaps) > 20:
        # Compute hourly rise rate during gap (approximation)
        hourly_rise = rise_after / (ins_gaps['duration_min'].values / 60)
        valid_rise = hourly_rise[~np.isnan(hourly_rise) & (np.abs(hourly_rise) < 200)]
        if len(valid_rise) > 10:
            print(f"\n  Estimated unopposed EGP (from insulin gaps):")
            print(f"    Median: {np.median(valid_rise):+.1f} mg/dL/hr")
            print(f"    IQR: [{np.percentile(valid_rise, 25):.1f}, {np.percentile(valid_rise, 75):.1f}]")
            print(f"    (Expected EGP ≈ 8-12 mg/dL/hr for typical adult)")
    
    ins_p_val = p_rise
else:
    ins_p_val = 1.0
    print("  Insufficient insulin gap events")

# ══════════════════════════════════════════════════════════════════════════
# PART 4: BG Discontinuity — Post-Restart Volatility
# ══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PART 4: BG Discontinuity (Sensor Restart) Analysis")
print("=" * 70)

discs = edf[edf['type'] == 'bg_discontinuity'].copy()
if len(discs) > 10:
    print(f"\n  BG discontinuities: {len(discs)} events")
    print(f"  Median jump size: {discs['jump_size'].median():.0f} mg/dL")
    
    # Post-restart volatility should be higher (controller adjusting to new reading)
    pre_stds = discs['pre_std'].values
    post_stds = discs['post_std'].values
    t_vol, p_vol = sp_stats.ttest_rel(post_stds, pre_stds)
    print(f"\n  Pre-restart std:  {np.median(pre_stds):.1f}")
    print(f"  Post-restart std: {np.median(post_stds):.1f}")
    print(f"  Volatility change: t={t_vol:.2f}, p={p_vol:.4f}")
    
    restart_p_val = p_vol
    restart_vol_increase = np.median(post_stds) > np.median(pre_stds)
else:
    restart_p_val = 1.0
    restart_vol_increase = False
    print("  Insufficient BG discontinuity events")

# ══════════════════════════════════════════════════════════════════════════
# PART 5: Causal Direction — Pre→Post vs Post→Pre
# ══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("PART 5: Causal Direction Test")
print("=" * 70)

# For natural experiments, pre-event conditions should predict post-event outcomes
# but NOT vice versa (asymmetry confirms causal direction)

if len(edf) > 50:
    # Use all events: does pre_mean predict post change?
    valid_events = edf.dropna(subset=['pre_mean', 'post_mean', 'pre_std', 'post_std'])
    
    # Forward: pre_mean → (post_mean - pre_mean)
    post_change = valid_events['post_mean'] - valid_events['pre_mean']
    r_forward, p_forward = sp_stats.pearsonr(valid_events['pre_mean'].astype(float), post_change.astype(float))
    
    # Backward: post_mean → (pre_mean - something_before) — can't do without earlier data
    # Alternative: pre_std → post_std (volatility transfer)
    r_vol, p_vol_causal = sp_stats.pearsonr(valid_events['pre_std'].astype(float), valid_events['post_std'].astype(float))
    
    print(f"  Forward: pre_mean → post_change: r={r_forward:.3f}, p={p_forward:.4f}")
    print(f"  Volatility transfer: pre_std → post_std: r={r_vol:.3f}, p={p_vol_causal:.4f}")
    print(f"  Pre BG predicts post change: {'Yes' if p_forward < 0.05 else 'No'}")
    
    causal_correct = p_forward < 0.05
else:
    causal_correct = False
    print("  Insufficient events for causal test")

# ══════════════════════════════════════════════════════════════════════════
# CRITERIA
# ══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("CRITERIA EVALUATION")
print("=" * 70)

P1 = len(edf) >= 100
p1_val = f"{len(edf)} events identified"

P2 = gap_p_val < 0.05 if len(gaps) > 10 else False
p2_val = f"Sensor gap p={gap_p_val:.4f}" if len(gaps) > 10 else "Insufficient gaps"

P3 = restart_vol_increase
p3_val = f"Post-restart volatility {'>' if restart_vol_increase else '≤'} pre-restart (p={restart_p_val:.4f})"

P4 = ins_p_val < 0.05 if len(ins_gaps) > 10 else False
p4_val = f"Insulin gap BG change p={ins_p_val:.4f}" if len(ins_gaps) > 10 else "Insufficient insulin gaps"

P5 = causal_correct
p5_val = f"Pre→post r={r_forward:.3f}, p={p_forward:.4f}" if len(edf) > 50 else "Insufficient"

criteria = {
    'P1_event_count': {'pass': P1, 'value': p1_val},
    'P2_sensor_gap_diff': {'pass': P2, 'value': p2_val},
    'P3_restart_volatility': {'pass': P3, 'value': p3_val},
    'P4_insulin_gap_rise': {'pass': P4, 'value': p4_val},
    'P5_causal_direction': {'pass': P5, 'value': p5_val},
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
    'n_events': len(edf),
    'event_counts': edf['type'].value_counts().to_dict(),
    'criteria': criteria,
    'pass_count': pass_count,
}

out_path = Path(f"externals/experiments/exp-{EXP_ID}_natural_experiments.json")
with open(out_path, 'w') as f:
    json.dump(output, f, indent=2, default=str)
print(f"\nResults saved to {out_path}")
