"""
EXP-2812: State-Transition Override Audition Windows

Stream B (settings/operational) work — no biology claims.

Hypothesis: Patients who transition into elevated state (S0→S1) experience
deteriorating control for several days before recovering. If we could detect
the transition early and audition a temporary override (e.g., reduced ISF,
increased basal), would it improve outcomes?

This experiment:
1. Detects state transitions in 48h-window state series
2. Characterizes the BG/insulin/event profile around transitions
3. Identifies actionable transition signatures
4. Produces triage flags: which transitions warrant temporary profile overrides

5/5 PASS criteria:
P1: ≥10 patients with detectable S0→S1 transitions
P2: Pre-transition window shows distinct signature vs stable S0 windows
P3: Post-transition deterioration measurable (TIR or hypers worsens)
P4: Recovery characteristics differ by controller
P5: ≥3 patients qualify for actionable temporary-override triage flag

NO Stream A claims; recommendations are operational thresholds, not biology.
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path

OUT = Path('externals/experiments')
EXP = '2812'
TITLE = 'state_transition_audition'

print(f"=== EXP-{EXP}: State-Transition Override Audition ===\n")

# Load state assignments (48h windows)
sa = pd.read_parquet(OUT / 'exp-2810_state_assignments.parquet')
sa = sa.sort_values(['patient_id', 'time']).reset_index(drop=True)
print(f"Loaded {len(sa)} state windows for {sa['patient_id'].nunique()} patients")
print(f"Controllers: {sa['controller'].value_counts().to_dict()}")

# Detect transitions per patient
transitions = []
for pid, grp in sa.groupby('patient_id'):
    g = grp.sort_values('time').reset_index(drop=True)
    g['prev_state'] = g['state'].shift(1)
    trans = g[g['state'] != g['prev_state']].dropna(subset=['prev_state']).copy()
    trans['transition'] = (trans['prev_state'].astype(int).astype(str)
                           .radd('S') + '->S' + trans['state'].astype(int).astype(str))
    transitions.append(trans)
trans_df = pd.concat(transitions, ignore_index=True)
print(f"\nDetected {len(trans_df)} state transitions across {trans_df['patient_id'].nunique()} patients")
print(f"Transition types:\n{trans_df['transition'].value_counts().to_dict()}")

# P1: enough patients with S0→S1 (deterioration entry)
s0_to_s1 = trans_df[trans_df['transition'] == 'S0->S1']
n_s0s1_patients = s0_to_s1['patient_id'].nunique()
P1 = n_s0s1_patients >= 10
print(f"\nP1: {n_s0s1_patients} patients with S0->S1 transitions (>=10? {P1})")

# Characterize pre/post windows
# For each transition, get window before (S0 baseline) and window after (S1 entry)
pre_post = []
for pid, grp in sa.groupby('patient_id'):
    g = grp.sort_values('time').reset_index(drop=True)
    g['prev_state'] = g['state'].shift(1)
    for i in range(1, len(g)):
        if g.loc[i, 'state'] == 1 and g.loc[i, 'prev_state'] == 0:
            # pre-transition: last S0 window
            pre = g.loc[i-1]
            post = g.loc[i]
            # next 1-2 windows after entering S1
            recovery_windows = g.loc[i:min(i+3, len(g)-1)]
            recovery_pct = (recovery_windows['state'] == 0).mean()
            pre_post.append({
                'patient_id': pid,
                'controller': pre['controller'],
                'transition_time': post['time'],
                'pre_mean_bg': pre['mean_glucose'],
                'post_mean_bg': post['mean_glucose'],
                'pre_pct_high': pre['pct_high'],
                'post_pct_high': post['pct_high'],
                'pre_pct_in_range': pre['pct_in_range'],
                'post_pct_in_range': post['pct_in_range'],
                'pre_iob': pre['mean_iob'],
                'post_iob': post['mean_iob'],
                'pre_carb_load': pre['carb_load'],
                'post_carb_load': post['carb_load'],
                'pre_volatility': pre['bg_volatility'],
                'post_volatility': post['bg_volatility'],
                'recovery_fraction_3w': recovery_pct,
            })
pp = pd.DataFrame(pre_post)
print(f"\nPre/post records: {len(pp)} for {pp['patient_id'].nunique()} patients")

# P2: pre-transition signature vs stable S0
stable_s0 = sa[sa['state'] == 0].copy()
# A "stable" S0 window is followed by another S0
stable_s0_idx = []
for pid, grp in sa.groupby('patient_id'):
    g = grp.sort_values('time').reset_index(drop=True)
    g['next_state'] = g['state'].shift(-1)
    for i in range(len(g)-1):
        if g.loc[i, 'state'] == 0 and g.loc[i, 'next_state'] == 0:
            stable_s0_idx.append((pid, g.loc[i, 'time']))
stable_set = set(stable_s0_idx)
sa_lookup = sa.set_index(['patient_id', 'time'])
stable_records = sa_lookup.loc[[k for k in stable_set if k in sa_lookup.index]].reset_index()
print(f"\nStable S0 windows: {len(stable_records)}")

# Compare pre-transition vs stable
sig_metrics = ['mean_glucose', 'pct_high', 'mean_iob', 'carb_load', 'bg_volatility']
sig_table = []
for m in sig_metrics:
    pre_vals = pp[f'pre_{m}'] if f'pre_{m}' in pp.columns else None
    if pre_vals is None: continue
    stable_vals = stable_records[m]
    pre_med = float(pre_vals.median())
    stable_med = float(stable_vals.median())
    delta_pct = (pre_med - stable_med) / abs(stable_med) * 100 if stable_med != 0 else float('nan')
    sig_table.append({
        'metric': m, 'pre_transition_median': round(pre_med, 3),
        'stable_s0_median': round(stable_med, 3), 'delta_pct': round(delta_pct, 1)
    })
sig_df = pd.DataFrame(sig_table)
print(f"\nPre-transition signature vs stable S0:")
print(sig_df.to_string(index=False))
# P2: at least 2 metrics differ by >15%
p2_diff_count = (sig_df['delta_pct'].abs() > 15).sum()
P2 = p2_diff_count >= 2
print(f"P2: {p2_diff_count} metrics differ >15% (>=2? {P2})")

# P3: post-transition deterioration
delta_tir = (pp['post_pct_in_range'] - pp['pre_pct_in_range']).median()
delta_high = (pp['post_pct_high'] - pp['pre_pct_high']).median()
P3 = delta_tir < -2 or delta_high > 2
print(f"\nP3: median ΔTIR={delta_tir:.1f}pp, ΔHigh={delta_high:.1f}pp (deterioration? {P3})")

# P4: recovery by controller
recovery_by_ctrl = pp.groupby('controller')['recovery_fraction_3w'].agg(['mean', 'median', 'count'])
print(f"\nP4: Recovery by controller:")
print(recovery_by_ctrl)
P4 = recovery_by_ctrl['median'].std() > 0.05  # meaningful between-controller difference
print(f"P4: controller recovery medians differ ({recovery_by_ctrl['median'].std():.3f} std, >0.05? {P4})")

# P5: triage flags
# Flag: patient has multiple S0->S1 transitions with low recovery
flag_records = []
for pid, grp in pp.groupby('patient_id'):
    n_trans = len(grp)
    median_recovery = grp['recovery_fraction_3w'].median()
    median_post_high = grp['post_pct_high'].median()
    median_pre_carb = grp['pre_carb_load'].median()
    if n_trans >= 2 and median_recovery < 0.4 and median_post_high > 30:
        flag_records.append({
            'patient_id': pid,
            'controller': grp['controller'].iloc[0],
            'n_transitions': n_trans,
            'median_recovery_fraction': round(median_recovery, 3),
            'median_post_pct_high': round(median_post_high, 1),
            'median_pre_carb_load': round(median_pre_carb, 1),
            'recommendation': 'Consider temporary tighter ISF/basal profile during early S0->S1 detection',
        })
flags = pd.DataFrame(flag_records)
print(f"\nP5: Triage flags: {len(flags)}")
if len(flags) > 0:
    print(flags.to_string(index=False))
P5 = len(flags) >= 3
print(f"P5: {len(flags)} actionable triage flags (>=3? {P5})")

# Save
pp.to_parquet(OUT / f'exp-{EXP}_pre_post_transitions.parquet', index=False)
flags.to_parquet(OUT / f'exp-{EXP}_triage_flags.parquet', index=False)
trans_df.to_parquet(OUT / f'exp-{EXP}_all_transitions.parquet', index=False)

passes = [P1, P2, P3, P4, P5]
result = {
    'experiment': f'EXP-{EXP}',
    'title': TITLE,
    'stream': 'B (settings/operational triage)',
    'conflation_risk': 'LOW (no biology claims)',
    'n_state_windows': int(len(sa)),
    'n_patients': int(sa['patient_id'].nunique()),
    'n_transitions_total': int(len(trans_df)),
    'transition_breakdown': trans_df['transition'].value_counts().to_dict(),
    'n_s0_to_s1_patients': int(n_s0s1_patients),
    'n_pre_post_records': int(len(pp)),
    'signature_table': sig_df.to_dict('records'),
    'p2_metrics_diff_15pct': int(p2_diff_count),
    'delta_tir_post_transition': round(float(delta_tir), 2),
    'delta_high_post_transition': round(float(delta_high), 2),
    'recovery_by_controller': {k: {kk: float(vv) for kk, vv in v.items()} for k, v in recovery_by_ctrl.to_dict('index').items()},
    'n_triage_flags': int(len(flags)),
    'pass_criteria': {
        'P1_>=10_patients_with_S0_S1': bool(P1),
        'P2_pre_transition_signature': bool(P2),
        'P3_post_deterioration': bool(P3),
        'P4_controller_recovery_differs': bool(P4),
        'P5_>=3_actionable_triage': bool(P5),
    },
    'pass_count': int(sum(passes)),
    'verdict': f"{sum(passes)}/5 PASS",
    'guardrail_compliance': {
        'G1_counterfactual_bands': 'N/A (Stream B)',
        'G2_no_streamA_as_setting': 'PASS (no Stream A inputs)',
        'G3_controller_confounded_label': 'N/A (no biology claim)',
        'G4_stream_declaration': 'PASS (Stream B declared)',
        'G5_triage_no_conflation': 'PASS (operational only)',
    },
}
with open(OUT / f'exp-{EXP}_{TITLE}.json', 'w') as f:
    json.dump(result, f, indent=2, default=str)

print(f"\n=== VERDICT: {sum(passes)}/5 PASS ===")
print(f"Saved: exp-{EXP}_{TITLE}.json + 3 parquets")
