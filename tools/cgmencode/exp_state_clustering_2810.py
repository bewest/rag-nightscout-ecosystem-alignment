#!/usr/bin/env python3
"""
EXP-2810: 48h Metabolic State Clustering & Persistence
========================================================

Rationale (REOPENED from incorrectly-closed 72h line):
  Prior EXP-2802 tested whether 72h BG history predicts NEXT BG and found
  reverse-causation. That was the WRONG test.

  The correct hypothesis: a 48h rolling window characterizes a discrete
  metabolic STATE (e.g., empty / moderate / full / overflowing) that:
    (a) persists on a 1-3 day planning horizon
    (b) is useful as a CONTEXTUAL covariate (not a BG predictor)
    (c) may decouple ISF↔basal confounding (EXP-2737 unfinished business)
    (d) supports treatment-audition windows (try a setting, observe over state)

  This experiment establishes whether the state structure EXISTS at all.
  EXP-2811 will test whether it decouples ISF↔basal.
  EXP-2812 will test whether it predicts override response.

Method:
  1. Compute 48h rolling features per patient (non-overlapping daily snapshots):
       - mean_glucose, std_glucose
       - pct_high (>180), pct_low (<70), pct_in_range
       - mean_iob, mean_cob
       - insulin_load (sum bolus + delivered basal)
       - carb_load (sum carbs)
       - bg_volatility (std of glucose_roc)
  2. Cluster windows (KMeans, k=3..5) using standardized features
  3. Test cluster physiological interpretability (do clusters separate on
     mean_BG, pct_high, etc. with effect sizes)
  4. Compute Markov transition matrix between consecutive 48h windows
  5. Measure state persistence (diagonal probability)

Success criteria:
  P1: Optimal k found by silhouette > 0.25 (modest but real structure)
  P2: Clusters interpretable: at least one "high"/"low"/"moderate" pattern
      with mean_BG separation > 30 mg/dL between extreme states
  P3: State persistence: diagonal transition probability > 0.45
      (states last long enough to plan around — at least 1-day window
       has >45% chance of same state next window)
  P4: State distribution is non-degenerate: no cluster < 5% of windows
  P5: Per-patient state usage varies (not all patients in same single state)
"""

import json
import sys
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats as sp_stats
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

warnings.filterwarnings('ignore')

EXP_ID = 2810
TITLE = "48h Metabolic State Clustering & Persistence"
EXCLUDE = {'odc-84181797', 'h', 'j'}

# ── Data Loading ──────────────────────────────────────────────────────────
print(f"[EXP-{EXP_ID}] {TITLE}")
print("=" * 70)

grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
grid = grid[~grid['patient_id'].isin(EXCLUDE)].copy()
grid = grid.sort_values(['patient_id', 'time']).reset_index(drop=True)

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

# ── 48h Window Feature Extraction ────────────────────────────────────────
# Use NON-OVERLAPPING daily snapshots (1 row per patient per calendar day)
# Features computed over the trailing 48h window.

WINDOW_HOURS = 48
STEP_HOURS = 24  # one snapshot per day
ROWS_PER_HOUR = 12

print(f"\nComputing 48h rolling features (step={STEP_HOURS}h)...")

windows_list = []
for pid in patients:
    pdata = grid[grid['patient_id'] == pid].copy().reset_index(drop=True)
    if len(pdata) < WINDOW_HOURS * ROWS_PER_HOUR:
        continue

    # Compute scheduled basal delivered (correct semantics from prior memory)
    actual_basal = (pdata['net_basal'].fillna(0) +
                    pdata['scheduled_basal_rate'].fillna(0)).clip(lower=0) / 12.0

    n = len(pdata)
    win_size = WINDOW_HOURS * ROWS_PER_HOUR
    step_size = STEP_HOURS * ROWS_PER_HOUR

    # Take snapshots every STEP_HOURS, computing features over trailing window
    for end_idx in range(win_size, n, step_size):
        start_idx = end_idx - win_size
        wnd = pdata.iloc[start_idx:end_idx]
        bg = wnd['glucose'].values
        valid = ~np.isnan(bg)
        if valid.sum() < 0.5 * win_size:
            continue

        feats = {
            'patient_id': pid,
            'controller': pdata['controller'].iloc[end_idx - 1],
            'time': pdata['time'].iloc[end_idx - 1],
            'mean_glucose': np.nanmean(bg),
            'std_glucose': np.nanstd(bg),
            'pct_high': np.nanmean(bg > 180) * 100,
            'pct_low': np.nanmean(bg < 70) * 100,
            'pct_very_low': np.nanmean(bg < 54) * 100,
            'pct_in_range': np.nanmean((bg >= 70) & (bg <= 180)) * 100,
            'pct_very_high': np.nanmean(bg > 250) * 100,
            'mean_iob': np.nanmean(wnd['iob'].values),
            'mean_cob': np.nanmean(wnd['cob'].values),
            'insulin_load': (np.nansum(wnd['bolus'].values) +
                              np.nansum(wnd['bolus_smb'].values) +
                              np.nansum(actual_basal.iloc[start_idx:end_idx].values)),
            'carb_load': np.nansum(wnd['carbs'].values),
            'bg_volatility': np.nanstd(wnd['glucose_roc'].values),
            'time_above_250_hr': np.nansum(bg > 250) / ROWS_PER_HOUR,
            'time_below_70_hr': np.nansum(bg < 70) / ROWS_PER_HOUR,
        }
        windows_list.append(feats)

windows = pd.DataFrame(windows_list)
print(f"  {len(windows)} 48h-windows extracted across {windows['patient_id'].nunique()} patients")

# ── Clustering ────────────────────────────────────────────────────────────
feature_cols = ['mean_glucose', 'std_glucose', 'pct_high', 'pct_low',
                'pct_in_range', 'mean_iob', 'mean_cob', 'insulin_load',
                'carb_load', 'bg_volatility']

X = windows[feature_cols].fillna(0).values
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

print("\n── Cluster k selection ──")
print(f"{'k':>3} {'silhouette':>12} {'inertia':>12}")
sil_scores = {}
for k in range(2, 7):
    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = km.fit_predict(X_scaled)
    sil = silhouette_score(X_scaled, labels, sample_size=min(5000, len(X_scaled)))
    sil_scores[k] = (sil, km.inertia_, labels)
    print(f"{k:>3} {sil:>12.3f} {km.inertia_:>12.0f}")

best_k = max(sil_scores, key=lambda k: sil_scores[k][0])
best_sil, _, best_labels = sil_scores[best_k]
print(f"\nBest k={best_k} (silhouette={best_sil:.3f})")

windows['state'] = best_labels

# ── Cluster characterization ──────────────────────────────────────────────
print(f"\n── State characterization (k={best_k}) ──")
state_summary = windows.groupby('state')[feature_cols + ['time_above_250_hr', 'time_below_70_hr']].mean()
state_counts = windows['state'].value_counts().sort_index()
print(f"{'state':>5} {'n':>6} {'mean_BG':>8} {'pct_high':>9} {'pct_low':>8} "
      f"{'pct_TIR':>8} {'volatility':>11} {'insulin':>9} {'carbs':>8}")
state_labels = {}
for s in sorted(state_counts.index):
    row = state_summary.loc[s]
    n = state_counts.loc[s]
    print(f"{s:>5} {n:>6} {row['mean_glucose']:>8.1f} "
          f"{row['pct_high']:>9.1f} {row['pct_low']:>8.1f} "
          f"{row['pct_in_range']:>8.1f} {row['bg_volatility']:>11.3f} "
          f"{row['insulin_load']:>9.1f} {row['carb_load']:>8.0f}")
    # Auto-label the state by dominant characteristic
    if row['pct_high'] > 40:
        state_labels[s] = 'STUCK_HIGH'
    elif row['pct_low'] > 5:
        state_labels[s] = 'HYPO_PRONE'
    elif row['pct_in_range'] > 70:
        state_labels[s] = 'WELL_CONTROLLED'
    else:
        state_labels[s] = 'MODERATE'

print(f"\nAuto-labels: {state_labels}")

bg_separation = state_summary['mean_glucose'].max() - state_summary['mean_glucose'].min()
print(f"BG separation (max-min cluster mean): {bg_separation:.1f} mg/dL")

min_pct = (state_counts / len(windows)).min() * 100
print(f"Smallest cluster: {min_pct:.1f}% of windows")

# ── State persistence: Markov transition matrix ───────────────────────────
print("\n── State persistence (Markov transitions) ──")
persistence_per_patient = []
for pid, pdata in windows.groupby('patient_id'):
    pdata = pdata.sort_values('time').reset_index(drop=True)
    if len(pdata) < 2:
        continue
    transitions = list(zip(pdata['state'].values[:-1], pdata['state'].values[1:]))
    n_trans = len(transitions)
    if n_trans < 5:
        continue
    same_state = sum(1 for a, b in transitions if a == b)
    persistence_per_patient.append({
        'patient_id': pid,
        'n_transitions': n_trans,
        'persistence': same_state / n_trans
    })

pers_df = pd.DataFrame(persistence_per_patient)
median_persistence = pers_df['persistence'].median()
print(f"  Median per-patient persistence (1-day): {median_persistence:.3f}")
print(f"  N patients with ≥5 transitions: {len(pers_df)}")

# Population transition matrix
print("\n  Transition matrix (rows=from, cols=to, normalized by row):")
trans_pairs = []
for pid, pdata in windows.groupby('patient_id'):
    pdata = pdata.sort_values('time').reset_index(drop=True)
    for a, b in zip(pdata['state'].values[:-1], pdata['state'].values[1:]):
        trans_pairs.append((a, b))
trans_df = pd.DataFrame(trans_pairs, columns=['from', 'to'])
trans_matrix = pd.crosstab(trans_df['from'], trans_df['to'], normalize='index')
print(trans_matrix.round(3).to_string())

diag_prob = np.diag(trans_matrix.values).mean()
print(f"\n  Mean diagonal probability (state persistence): {diag_prob:.3f}")

# ── Per-patient state diversity ───────────────────────────────────────────
patient_state_diversity = windows.groupby('patient_id')['state'].nunique()
patients_in_multiple_states = (patient_state_diversity > 1).sum()
print(f"\n  Patients visiting >1 state: {patients_in_multiple_states}/{windows['patient_id'].nunique()}")

# ── Success criteria ──────────────────────────────────────────────────────
results = {
    'experiment_id': EXP_ID,
    'title': TITLE,
    'date': datetime.now().isoformat(),
    'n_patients': int(windows['patient_id'].nunique()),
    'n_windows': int(len(windows)),
    'window_hours': WINDOW_HOURS,
    'step_hours': STEP_HOURS,
    'best_k': int(best_k),
    'best_silhouette': float(best_sil),
    'silhouette_by_k': {int(k): float(s[0]) for k, s in sil_scores.items()},
    'state_labels': {int(k): v for k, v in state_labels.items()},
    'state_distribution_pct': {int(k): float(v / len(windows) * 100) for k, v in state_counts.items()},
    'bg_separation': float(bg_separation),
    'min_cluster_pct': float(min_pct),
    'median_persistence': float(median_persistence),
    'mean_diagonal_persistence': float(diag_prob),
    'patients_in_multiple_states': int(patients_in_multiple_states),
    'state_summary': state_summary.round(3).to_dict(),
    'transition_matrix': trans_matrix.round(4).to_dict(),
    'criteria': {
        'P1_silhouette_gt_0.25': bool(best_sil > 0.25),
        'P2_bg_separation_gt_30': bool(bg_separation > 30),
        'P3_persistence_gt_0.45': bool(diag_prob > 0.45),
        'P4_no_degenerate_cluster': bool(min_pct >= 5.0),
        'P5_patients_diverse': bool(patients_in_multiple_states >= 0.5 * windows['patient_id'].nunique()),
    }
}
results['n_pass'] = sum(1 for v in results['criteria'].values() if v)
results['pass_count'] = f"{results['n_pass']}/5"

print("\n" + "=" * 70)
print(f"SUCCESS CRITERIA ({results['pass_count']} PASS)")
print("=" * 70)
for k, v in results['criteria'].items():
    print(f"  {'✓' if v else '✗'}  {k}")

# ── Save results ──────────────────────────────────────────────────────────
out_dir = Path("externals/experiments")
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / f"exp-{EXP_ID}_state_clustering.json"
with open(out_path, 'w') as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nSaved: {out_path}")

# Save per-window state assignments for downstream experiments
state_path = out_dir / f"exp-{EXP_ID}_state_assignments.parquet"
windows.to_parquet(state_path)
print(f"Saved state assignments: {state_path}")
