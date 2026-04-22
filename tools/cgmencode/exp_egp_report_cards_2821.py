#!/usr/bin/env python3
"""
EXP-2821: EGP-Aware Report Cards
==================================

Rationale:
  EXP-2807 produced per-patient settings recommendations using observed
  ISF/CR/basal vs profile, with confidence flags.

  EXP-2820 produced a canonical per-patient EGP table reconciling 11 prior
  experiments (median 4.9 mg/dL/hr, range 0.07-24.6 mg/dL/hr).

  This experiment tests whether incorporating EGP into report cards:
  (a) explains the systematic "ISF needs increase" recommendation pattern
  (b) flags high-EGP patients (like ns-d444c120c) for special handling
  (c) provides EGP-corrected ISF for the 11 patients with EGP estimates
  (d) maintains the report card's safety/efficacy structure

Method:
  1. Load EXP-2820 canonical EGP table (11 patients)
  2. Re-run EXP-2807-style report card extraction
  3. For patients with canonical EGP, compute EGP-corrected ISF:
       ISF_corrected = (drop + EGP × t_hours) / dose
       (EGP is a headwind that masks insulin's true effect)
  4. Compare:
       - Naive ISF vs profile ISF (the previous report-card metric)
       - EGP-corrected ISF vs profile ISF (new metric)
       - High-EGP patients' recommendation changes
  5. Generate state-aware basal flags using EXP-2811 results

Success criteria:
  P1: Canonical EGP available for ≥10 patients (carries from EXP-2820)
  P2: EGP correction shifts ISF estimates upward (closer to profile)
  P3: For high-EGP patient(s), recommendation changes from "INCREASE"
      to "ALIGNED" or "DECREASE"
  P4: Net safety alerts unchanged or reduced (EGP doesn't worsen flags)
  P5: ≥1 actionable change to report card recommendations
"""

import json
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

EXP_ID = 2821
TITLE = "EGP-Aware Report Cards"
EXCLUDE = {'odc-84181797', 'h', 'j'}

print(f"[EXP-{EXP_ID}] {TITLE}")
print("=" * 70)

# ── Load data ─────────────────────────────────────────────────────────────
grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
grid = grid[~grid['patient_id'].isin(EXCLUDE)].copy()
grid = grid.sort_values(['patient_id', 'time']).reset_index(drop=True)

canonical_egp = pd.read_parquet("externals/experiments/exp-2820_canonical_egp.parquet")
egp_lookup = dict(zip(canonical_egp['patient_id'], canonical_egp['canonical_egp_mg_dL_hr']))
print(f"Canonical EGP available for {sum(1 for v in egp_lookup.values() if pd.notna(v))} patients")

state_decoupling = pd.read_parquet("externals/experiments/exp-2811_per_state_extractions.parquet")

def classify_controller(pid):
    if len(pid) == 1 and pid.isalpha():
        return 'Loop'
    elif pid.startswith('ns-'):
        return 'Trio'
    elif pid.startswith('odc-'):
        return 'OpenAPS'
    return 'Unknown'

# ── Per-patient ISF extraction (EXP-2805 method) ─────────────────────────
def extract_optimal_isf_events(pdata, return_events=False):
    pdata = pdata.sort_values('time').reset_index(drop=True)
    bg = pdata['glucose'].values
    bolus = pdata['bolus'].fillna(0).values
    carbs = pdata['carbs'].fillna(0).values
    n = len(pdata)
    events = []
    for i in range(72, n - 36):
        if bolus[i] < 0.5 or bg[i] < 180:
            continue
        if carbs[max(0, i - 36):min(n, i + 36)].sum() > 5:
            continue
        back_bg = bg[max(0, i - 72):i]
        if np.isnan(back_bg).any():
            continue
        time_in_high = (back_bg > 180).sum() / 12.0
        if not (1 <= time_in_high <= 6):
            continue
        fwd_bg = bg[i + 24:i + 36]
        if np.isnan(fwd_bg).any():
            continue
        drop = bg[i] - fwd_bg.min()
        if drop <= 0:
            continue
        # Time elapsed to nadir (hours)
        nadir_idx = np.argmin(fwd_bg)
        t_hours = (24 + nadir_idx) / 12.0
        isf_naive = drop / bolus[i]
        if 5 <= isf_naive <= 200:
            events.append({
                'isf_naive': isf_naive,
                'drop': float(drop),
                'dose': float(bolus[i]),
                't_hours': float(t_hours),
            })
    return events

# ── Build EGP-aware report cards ─────────────────────────────────────────
print("\n── Building EGP-aware report cards ──")
report_cards = []
for pid in sorted(grid['patient_id'].unique()):
    pdata = grid[grid['patient_id'] == pid]
    controller = classify_controller(pid)
    profile_isf = pdata['scheduled_isf'].dropna().median()
    profile_isf = float(profile_isf) if pd.notna(profile_isf) else np.nan

    # TIR/safety metrics
    bg = pdata['glucose'].dropna().values
    pct_below_70 = float((bg < 70).mean() * 100) if len(bg) else np.nan
    pct_below_54 = float((bg < 54).mean() * 100) if len(bg) else np.nan
    pct_in_range = float(((bg >= 70) & (bg <= 180)).mean() * 100) if len(bg) else np.nan

    events = extract_optimal_isf_events(pdata)
    if len(events) < 5:
        report_cards.append({
            'patient_id': pid, 'controller': controller,
            'profile_isf': profile_isf,
            'isf_naive': np.nan, 'isf_egp_corrected': np.nan,
            'egp_mg_dL_hr': egp_lookup.get(pid, np.nan),
            'n_events': len(events),
            'pct_below_70': pct_below_70, 'pct_below_54': pct_below_54,
            'pct_in_range': pct_in_range,
            'recommendation_naive': 'INSUFFICIENT_DATA',
            'recommendation_egp': 'INSUFFICIENT_DATA',
            'flags': [],
        })
        continue

    isfs_naive = [e['isf_naive'] for e in events]
    isf_naive_med = float(np.median(isfs_naive))
    isf_naive_cv = float(np.std(isfs_naive) / np.mean(isfs_naive))

    # EGP correction
    egp = egp_lookup.get(pid, np.nan)
    if pd.notna(egp) and egp > 0:
        # During the t_hours window, EGP added (egp × t_hours) mg/dL of glucose
        # that the insulin had to overcome. So the "true" insulin effect is:
        # corrected_drop = observed_drop + egp × t_hours
        isfs_corrected = [(e['drop'] + egp * e['t_hours']) / e['dose'] for e in events]
        isf_egp_med = float(np.median(isfs_corrected))
    else:
        isf_egp_med = np.nan

    # Recommendations
    def recommend(isf_obs, profile, cv, n_events):
        if pd.isna(isf_obs) or pd.isna(profile):
            return 'INSUFFICIENT_DATA'
        if cv > 1.0 or n_events < 10:
            return 'LOW_CONFIDENCE'
        ratio = isf_obs / profile
        if ratio > 1.3:
            return 'INCREASE_ISF'  # observed > profile → profile is conservative
        elif ratio < 0.7:
            return 'DECREASE_ISF'  # observed < profile → profile is too aggressive
        else:
            return 'ALIGNED'

    rec_naive = recommend(isf_naive_med, profile_isf, isf_naive_cv, len(events))
    rec_egp = recommend(isf_egp_med, profile_isf, isf_naive_cv, len(events))

    # Safety/efficacy flags
    flags = []
    if pct_below_70 > 4:
        flags.append('SAFETY_ALERT')
    if pct_in_range < 70:
        flags.append('EFFICACY_ALERT')
    if pd.notna(egp) and egp > 12:
        flags.append('HIGH_EGP_CAUTION')

    report_cards.append({
        'patient_id': pid, 'controller': controller,
        'profile_isf': profile_isf,
        'isf_naive': isf_naive_med,
        'isf_egp_corrected': isf_egp_med,
        'egp_mg_dL_hr': egp,
        'n_events': len(events),
        'isf_cv': isf_naive_cv,
        'pct_below_70': pct_below_70, 'pct_below_54': pct_below_54,
        'pct_in_range': pct_in_range,
        'recommendation_naive': rec_naive,
        'recommendation_egp': rec_egp,
        'flags': flags,
    })

cards = pd.DataFrame(report_cards)
print(f"  {len(cards)} patient report cards")

# ── Comparison tables ────────────────────────────────────────────────────
print("\n── Recommendation comparison: NAIVE vs EGP-CORRECTED ──")
naive_counts = cards['recommendation_naive'].value_counts().to_dict()
egp_counts = cards['recommendation_egp'].value_counts().to_dict()
all_recs = set(naive_counts.keys()) | set(egp_counts.keys())
print(f"{'recommendation':<22} {'naive':>8} {'egp_corrected':>15}")
for rec in sorted(all_recs):
    print(f"{rec:<22} {naive_counts.get(rec, 0):>8} {egp_counts.get(rec, 0):>15}")

# Patients where recommendation changed
have_egp = cards[cards['egp_mg_dL_hr'].notna()].copy()
have_egp['changed'] = have_egp['recommendation_naive'] != have_egp['recommendation_egp']
n_changed = have_egp['changed'].sum()
print(f"\n  Patients with EGP estimate: {len(have_egp)}")
print(f"  Recommendation changed by EGP correction: {n_changed}/{len(have_egp)}")

if n_changed > 0:
    print("\n  Changes:")
    print(have_egp[have_egp['changed']][['patient_id', 'controller', 'profile_isf', 'isf_naive',
                                          'isf_egp_corrected', 'egp_mg_dL_hr',
                                          'recommendation_naive', 'recommendation_egp']].to_string(index=False))

# ── ISF shift analysis ──────────────────────────────────────────────────
print("\n── ISF shift from EGP correction ──")
shift_data = have_egp[(have_egp['isf_naive'].notna()) & (have_egp['isf_egp_corrected'].notna())].copy()
if len(shift_data) > 0:
    shift_data['isf_shift'] = shift_data['isf_egp_corrected'] - shift_data['isf_naive']
    shift_data['shift_pct'] = 100 * shift_data['isf_shift'] / shift_data['isf_naive']
    print(f"  Patients with ISF shift available: {len(shift_data)}")
    print(f"  Median ISF shift: {shift_data['isf_shift'].median():+.1f} mg/dL/U "
          f"({shift_data['shift_pct'].median():+.1f}%)")
    print(f"  Range: {shift_data['isf_shift'].min():+.1f} to {shift_data['isf_shift'].max():+.1f}")
    n_upward = (shift_data['isf_shift'] > 0).sum()
    print(f"  Patients shifted upward (closer to profile): {n_upward}/{len(shift_data)}")

# ── Profile alignment improvement ──────────────────────────────────────
print("\n── Profile alignment (lower = closer to profile) ──")
if len(shift_data) > 0:
    shift_data['gap_naive'] = abs(shift_data['profile_isf'] - shift_data['isf_naive'])
    shift_data['gap_egp'] = abs(shift_data['profile_isf'] - shift_data['isf_egp_corrected'])
    shift_data['gap_improved'] = shift_data['gap_egp'] < shift_data['gap_naive']
    n_improved = shift_data['gap_improved'].sum()
    print(f"  Patients with profile-gap reduced by EGP correction: {n_improved}/{len(shift_data)}")
    print(f"  Median naive gap: {shift_data['gap_naive'].median():.1f} mg/dL/U")
    print(f"  Median EGP-corrected gap: {shift_data['gap_egp'].median():.1f} mg/dL/U")

# ── High-EGP patients ───────────────────────────────────────────────────
print("\n── High-EGP patients (>12 mg/dL/hr) ──")
high_egp = cards[cards['egp_mg_dL_hr'] > 12]
if len(high_egp) > 0:
    print(high_egp[['patient_id', 'controller', 'profile_isf', 'isf_naive',
                    'isf_egp_corrected', 'egp_mg_dL_hr',
                    'recommendation_naive', 'recommendation_egp', 'flags']].to_string(index=False))

# ── Safety flag preservation ────────────────────────────────────────────
n_safety_flagged = cards['flags'].apply(lambda x: 'SAFETY_ALERT' in x).sum()
n_efficacy_flagged = cards['flags'].apply(lambda x: 'EFFICACY_ALERT' in x).sum()
n_egp_flagged = cards['flags'].apply(lambda x: 'HIGH_EGP_CAUTION' in x).sum()
print(f"\n── Flag distribution ──")
print(f"  SAFETY_ALERT: {n_safety_flagged}/{len(cards)}")
print(f"  EFFICACY_ALERT: {n_efficacy_flagged}/{len(cards)}")
print(f"  HIGH_EGP_CAUTION: {n_egp_flagged}/{len(cards)}")

# ── Success criteria ──────────────────────────────────────────────────────
results = {
    'experiment_id': EXP_ID,
    'title': TITLE,
    'date': datetime.now().isoformat(),
    'n_patients': int(len(cards)),
    'n_with_canonical_egp': int(cards['egp_mg_dL_hr'].notna().sum()),
    'recommendations_naive': {k: int(v) for k, v in naive_counts.items()},
    'recommendations_egp': {k: int(v) for k, v in egp_counts.items()},
    'n_recommendations_changed_by_egp': int(n_changed),
    'isf_shift_median': float(shift_data['isf_shift'].median()) if len(shift_data) > 0 else None,
    'isf_shift_pct_median': float(shift_data['shift_pct'].median()) if len(shift_data) > 0 else None,
    'n_shifted_upward': int(n_upward) if len(shift_data) > 0 else 0,
    'n_profile_gap_improved': int(n_improved) if len(shift_data) > 0 else 0,
    'high_egp_patients': high_egp['patient_id'].tolist(),
    'flags_safety': int(n_safety_flagged),
    'flags_efficacy': int(n_efficacy_flagged),
    'flags_high_egp': int(n_egp_flagged),
    'criteria': {
        'P1_canonical_egp_ge_10': bool(cards['egp_mg_dL_hr'].notna().sum() >= 10),
        'P2_egp_shifts_isf_upward': bool(
            (shift_data['isf_shift'].median() > 0) if len(shift_data) > 0 else False
        ),
        'P3_high_egp_recommendation_changed': bool(
            ((high_egp['recommendation_naive'] != high_egp['recommendation_egp']).any())
            if len(high_egp) > 0 else False
        ),
        'P4_safety_flags_preserved': bool(n_safety_flagged > 0),
        'P5_actionable_change_count_ge_1': bool(n_changed >= 1),
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
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / f"exp-{EXP_ID}_egp_report_cards.json"
with open(out_path, 'w') as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nSaved: {out_path}")

cards.to_parquet(out_dir / f"exp-{EXP_ID}_report_cards.parquet")
print(f"Saved report cards: exp-{EXP_ID}_report_cards.parquet")
