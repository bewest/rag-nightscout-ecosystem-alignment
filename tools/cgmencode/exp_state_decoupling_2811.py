#!/usr/bin/env python3
"""
EXP-2811: ISF↔Basal Decoupling via Metabolic State Stratification
==================================================================

Rationale:
  EXP-2737 found ISF and basal extraction errors correlate ρ=0.609 across
  patients (shared confounders) but joint optimization only gives +2.5% MAE.
  This is a longstanding open problem: the two settings are mathematically
  coupled because both affect BG dynamics in similar ways.

  Hypothesis: A 48h metabolic state covariate (EXP-2810) may break this
  coupling because:
    - In WELL_CONTROLLED state, basal is doing most of the work (small
      excursions, EGP cancelled) → basal is identifiable, ISF less so
    - In MODERATE/HIGH state, ISF (corrections) is doing most of the work
      → ISF is identifiable, basal is less so
  Stratifying by state should reduce the ISF↔basal error correlation
  within each state.

Method:
  1. Load EXP-2810 state assignments (48h windows × patients)
  2. For each patient × state, extract:
       a. ISF from corrections within that state (EXP-2805 method)
       b. Basal from low-IOB fasting periods within that state
  3. Compute residuals from profile (or population) for each
  4. Test whether |corr(ISF_resid, basal_resid)| within state
     < |corr(ISF_resid, basal_resid)| across all states (pooled)

Success criteria:
  P1: Per-state extraction succeeds for ≥10 patients in ≥1 state
  P2: Within-state ISF↔basal correlation is REDUCED vs pooled
      (pooled ρ should reproduce EXP-2737's ~0.6, within-state should be lower)
  P3: At least one state shows |ρ| < 0.3 (effective decoupling)
  P4: ISF varies by state for ≥5 patients (confirms state matters)
  P5: Basal varies by state for ≥5 patients (confirms state matters)
"""

import json
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

warnings.filterwarnings('ignore')

EXP_ID = 2811
TITLE = "ISF↔Basal Decoupling via Metabolic State"
EXCLUDE = {'odc-84181797', 'h', 'j'}

print(f"[EXP-{EXP_ID}] {TITLE}")
print("=" * 70)

# ── Load data ─────────────────────────────────────────────────────────────
grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
grid = grid[~grid['patient_id'].isin(EXCLUDE)].copy()
grid = grid.sort_values(['patient_id', 'time']).reset_index(drop=True)

state_assignments = pd.read_parquet("externals/experiments/exp-2810_state_assignments.parquet")
print(f"Grid: {len(grid)} rows × {grid['patient_id'].nunique()} patients")
print(f"State assignments: {len(state_assignments)} 48h windows")

# Map each grid row to a state via nearest preceding 48h window
def assign_state_to_rows(grid_p, sa_p):
    """For each row in grid_p, find the most recent 48h window state."""
    sa_p = sa_p.sort_values('time').reset_index(drop=True)
    grid_p = grid_p.sort_values('time').reset_index(drop=True)
    if len(sa_p) == 0:
        grid_p['state'] = -1
        return grid_p
    # Use merge_asof to assign state from the most recent window snapshot
    grid_p = pd.merge_asof(
        grid_p.sort_values('time'),
        sa_p[['time', 'state']].sort_values('time'),
        on='time', direction='backward'
    )
    grid_p['state'] = grid_p['state'].fillna(-1).astype(int)
    return grid_p

print("\nAssigning state to each row...")
parts = []
for pid in grid['patient_id'].unique():
    g = grid[grid['patient_id'] == pid].copy()
    sa = state_assignments[state_assignments['patient_id'] == pid].copy()
    parts.append(assign_state_to_rows(g, sa))
grid = pd.concat(parts, ignore_index=True)

state_counts_overall = grid['state'].value_counts().sort_index()
print(f"Row-level state distribution: {dict(state_counts_overall)}")

# ── Helper: per-patient×state ISF extraction ─────────────────────────────
def extract_isf_per_state(pdata):
    """ISF from optimal correction events within each state.

    Optimal event criteria (per EXP-2805):
      - Starting BG ≥ 180
      - Time-in-high (BG>180) for 1-6h before event
      - No carbs ±3h
      - Bolus delivered (correction)
      - Measure 2-3h BG drop / bolus dose
    """
    pdata = pdata.sort_values('time').reset_index(drop=True)
    bg = pdata['glucose'].values
    bolus = pdata['bolus'].fillna(0).values
    carbs = pdata['carbs'].fillna(0).values
    state = pdata['state'].values
    n = len(pdata)

    isf_by_state = {}
    for s in np.unique(state):
        if s < 0:
            continue
        events = []
        # Find correction events: bolus > 0.5U, no carbs ±36 rows (3h)
        for i in range(36, n - 36):
            if state[i] != s:
                continue
            if bolus[i] < 0.5:
                continue
            if bg[i] < 180:
                continue
            # No carbs window
            if carbs[max(0, i - 36):min(n, i + 36)].sum() > 5:
                continue
            # Time-in-high backward 1-6h
            back_bg = bg[max(0, i - 72):i]  # 6h
            if np.isnan(back_bg).any():
                continue
            time_in_high = (back_bg > 180).sum() / 12.0  # hours
            if not (1 <= time_in_high <= 6):
                continue
            # Measure BG 2-3h forward (24-36 rows)
            fwd_bg = bg[i + 24:i + 36]
            if np.isnan(fwd_bg).any():
                continue
            drop = bg[i] - fwd_bg.min()
            if drop <= 0:
                continue
            isf = drop / bolus[i]
            if 5 <= isf <= 200:  # plausible
                events.append(isf)
        if len(events) >= 5:
            isf_by_state[int(s)] = {
                'isf': float(np.median(events)),
                'cv': float(np.std(events) / np.mean(events)) if np.mean(events) > 0 else np.nan,
                'n_events': len(events),
            }
    return isf_by_state


def extract_basal_per_state(pdata):
    """Basal from low-IOB, no-meal fasting periods within each state.

    Method: compute mean BG drift (mg/dL/hr) during 2h windows where
      - IOB < 1.0 U (low active insulin)
      - No carbs ±2h
      - No bolus ±2h
      - State stable
    Then derived basal need ≈ mean_drift / ISF (using profile ISF as scale).
    Report drift directly (in mg/dL/hr) as a basal-adequacy proxy.
    Lower drift = basal closer to need; higher drift = basal under-delivers.
    """
    pdata = pdata.sort_values('time').reset_index(drop=True)
    bg = pdata['glucose'].values
    bolus = pdata['bolus'].fillna(0).values
    smb = pdata['bolus_smb'].fillna(0).values
    carbs = pdata['carbs'].fillna(0).values
    iob = pdata['iob'].fillna(0).values
    state = pdata['state'].values
    n = len(pdata)

    drift_by_state = {}
    for s in np.unique(state):
        if s < 0:
            continue
        drifts = []
        # Sample fasting windows
        for i in range(24, n - 24, 12):  # step every 1h, 2h windows
            if state[i] != s:
                continue
            # No bolus ±2h
            if bolus[max(0, i - 24):min(n, i + 24)].sum() > 0.1:
                continue
            if smb[max(0, i - 24):min(n, i + 24)].sum() > 0.1:
                continue
            # No carbs ±2h
            if carbs[max(0, i - 24):min(n, i + 24)].sum() > 5:
                continue
            # Low IOB
            if iob[i] > 1.0:
                continue
            # Compute drift over 2h
            window_bg = bg[i:i + 24]
            if np.isnan(window_bg).any():
                continue
            drift_hr = (window_bg[-1] - window_bg[0]) / 2.0  # mg/dL/hr
            drifts.append(drift_hr)
        if len(drifts) >= 5:
            drift_by_state[int(s)] = {
                'drift_mg_dL_hr': float(np.median(drifts)),
                'cv': float(np.std(drifts) / abs(np.mean(drifts))) if abs(np.mean(drifts)) > 0.1 else np.nan,
                'n_events': len(drifts),
            }
    return drift_by_state


# ── Extract per patient × state ──────────────────────────────────────────
print("\n── Extracting ISF and basal-drift per patient × state ──")
records = []
for pid in sorted(grid['patient_id'].unique()):
    pdata = grid[grid['patient_id'] == pid]
    isf_by_state = extract_isf_per_state(pdata)
    drift_by_state = extract_basal_per_state(pdata)
    for s in set(isf_by_state.keys()) | set(drift_by_state.keys()):
        rec = {
            'patient_id': pid,
            'state': s,
            'isf': isf_by_state.get(s, {}).get('isf', np.nan),
            'isf_n': isf_by_state.get(s, {}).get('n_events', 0),
            'basal_drift': drift_by_state.get(s, {}).get('drift_mg_dL_hr', np.nan),
            'basal_n': drift_by_state.get(s, {}).get('n_events', 0),
        }
        records.append(rec)

extraction = pd.DataFrame(records)
print(f"  {len(extraction)} patient×state extractions")
print(f"  Patients with ISF in any state: {extraction['isf'].notna().groupby(extraction['patient_id']).any().sum()}")
print(f"  Patients with basal drift in any state: {extraction['basal_drift'].notna().groupby(extraction['patient_id']).any().sum()}")

# Per-state summaries
print("\n── Per-state extraction summary ──")
for s in sorted(extraction['state'].unique()):
    sub = extraction[extraction['state'] == s]
    isf_n = sub['isf'].notna().sum()
    drift_n = sub['basal_drift'].notna().sum()
    isf_med = sub['isf'].median()
    drift_med = sub['basal_drift'].median()
    print(f"  State {s}: ISF n={isf_n}/{len(sub)} (median {isf_med:.1f}), "
          f"basal_drift n={drift_n}/{len(sub)} (median {drift_med:+.2f} mg/dL/hr)")

# ── ISF↔basal coupling analysis ──────────────────────────────────────────
print("\n── ISF↔Basal Coupling Analysis ──")

# Pooled (across all states) — should reproduce EXP-2737's ~0.6
pooled = extraction.dropna(subset=['isf', 'basal_drift'])
if len(pooled) >= 5:
    rho_pooled, p_pooled = sp_stats.spearmanr(pooled['isf'], pooled['basal_drift'])
    print(f"  POOLED (all states): n={len(pooled)}, ρ={rho_pooled:+.3f} (p={p_pooled:.3f})")
else:
    rho_pooled, p_pooled = np.nan, np.nan

# Within each state
within_state_rhos = {}
for s in sorted(extraction['state'].unique()):
    sub = extraction[(extraction['state'] == s)].dropna(subset=['isf', 'basal_drift'])
    if len(sub) >= 5:
        rho, p = sp_stats.spearmanr(sub['isf'], sub['basal_drift'])
        within_state_rhos[int(s)] = {'rho': float(rho), 'p': float(p), 'n': len(sub)}
        print(f"  STATE {s}: n={len(sub)}, ρ={rho:+.3f} (p={p:.3f})")

# Per-patient state variation
print("\n── Per-patient state variation ──")
patient_isf_var = []
patient_basal_var = []
for pid, pdata in extraction.groupby('patient_id'):
    isfs = pdata['isf'].dropna()
    drifts = pdata['basal_drift'].dropna()
    if len(isfs) >= 2:
        patient_isf_var.append({
            'patient_id': pid,
            'isf_state_diff': float(isfs.max() - isfs.min()),
            'isf_states': len(isfs)
        })
    if len(drifts) >= 2:
        patient_basal_var.append({
            'patient_id': pid,
            'drift_state_diff': float(drifts.max() - drifts.min()),
            'drift_states': len(drifts)
        })

isf_varying = sum(1 for p in patient_isf_var if p['isf_state_diff'] > 5)
basal_varying = sum(1 for p in patient_basal_var if p['drift_state_diff'] > 1)
print(f"  Patients with ISF varying by state (>5 mg/dL/U): {isf_varying}/{len(patient_isf_var)}")
print(f"  Patients with basal-drift varying by state (>1 mg/dL/hr): {basal_varying}/{len(patient_basal_var)}")

# ── Success criteria ─────────────────────────────────────────────────────
n_with_isf = extraction.groupby('state')['isf'].apply(lambda x: x.notna().sum())
states_with_10 = (n_with_isf >= 10).sum()

best_within_state_abs_rho = min(
    [abs(v['rho']) for v in within_state_rhos.values()],
    default=1.0
)

results = {
    'experiment_id': EXP_ID,
    'title': TITLE,
    'date': datetime.now().isoformat(),
    'n_patient_state_extractions': int(len(extraction)),
    'n_with_isf_per_state': {int(k): int(v) for k, v in n_with_isf.items()},
    'pooled_isf_basal_rho': float(rho_pooled) if pd.notna(rho_pooled) else None,
    'pooled_isf_basal_p': float(p_pooled) if pd.notna(p_pooled) else None,
    'within_state_isf_basal_rho': within_state_rhos,
    'best_within_state_abs_rho': float(best_within_state_abs_rho),
    'isf_varying_by_state_n': int(isf_varying),
    'basal_varying_by_state_n': int(basal_varying),
    'criteria': {
        'P1_extraction_ge_10_patients_one_state': bool(states_with_10 >= 1),
        'P2_within_state_decouples': bool(
            best_within_state_abs_rho < abs(rho_pooled) if pd.notna(rho_pooled) else False
        ),
        'P3_at_least_one_state_rho_lt_0.3': bool(best_within_state_abs_rho < 0.3),
        'P4_isf_varies_ge_5_patients': bool(isf_varying >= 5),
        'P5_basal_varies_ge_5_patients': bool(basal_varying >= 5),
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
out_path = out_dir / f"exp-{EXP_ID}_state_decoupling.json"
with open(out_path, 'w') as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nSaved: {out_path}")

# Save the extraction table for downstream use
extraction.to_parquet(out_dir / f"exp-{EXP_ID}_per_state_extractions.parquet")
print(f"Saved per-state extractions: exp-{EXP_ID}_per_state_extractions.parquet")
