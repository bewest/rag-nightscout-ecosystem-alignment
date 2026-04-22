#!/usr/bin/env python3
"""
EXP-2823: EGP × State Interaction
==================================

Question: Does the slow-timescale state regime (EXP-2810) modulate per-event
EGP, or is canonical EGP constant per patient regardless of state?

Two non-exclusive sub-hypotheses:
  H1 (between-patient): High-EGP patients spend disproportionately more
     time in State 1 (high-glucose regime). EGP is a covariate of state.
  H2 (within-patient): EGP estimated within State 1 windows is
     systematically higher than EGP estimated within State 0 windows
     for the same patient. State captures a meaningful EGP variation.

Method:
  H1: Per-patient (canonical EGP, %time in State 1) → Spearman correlation.
  H2: For each patient with both states present, compute EGP estimate
      separately within State 0 and State 1 windows using the equilibrium
      method (basal × ISF, equilibrium when BG flat). Compare distributions.

Multi-layer architectural value:
  - If H1 holds: state can serve as a CHEAP PROXY for EGP regime
    (state is computable from BG alone; EGP needs basal + ISF data)
  - If H2 holds: EGP is not a static patient property; per-event EGP
    correction needs state-dependent EGP, not patient-mean EGP

Success criteria:
  P1: Per-patient %State1 has |ρ| > 0.4 with canonical EGP
  P2: ≥5 patients have ≥3 windows in EACH state (enables H2 test)
  P3: Median EGP_State1 / EGP_State0 > 1.0 across patients with both states
  P4: At least 1 patient has statistically distinguishable EGP between states
  P5: State-stratified EGP improves explanatory power vs static EGP
      (variance of within-patient ISF residual after state-EGP correction
       < variance after static-EGP correction)
"""

import json
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

warnings.filterwarnings('ignore')

EXP_ID = 2823
TITLE = "EGP × State Interaction"
EXCLUDE = {'odc-84181797', 'h', 'j'}

print(f"[EXP-{EXP_ID}] {TITLE}")
print("=" * 70)

# ── Data ─────────────────────────────────────────────────────────────────
grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
grid = grid[~grid['patient_id'].isin(EXCLUDE)].copy()
grid = grid.sort_values(['patient_id', 'time']).reset_index(drop=True)
state = pd.read_parquet("externals/experiments/exp-2810_state_assignments.parquet")
canonical_egp = pd.read_parquet("externals/experiments/exp-2820_canonical_egp.parquet")
events = pd.read_parquet("externals/experiments/exp-2831_correction_events.parquet") if Path("externals/experiments/exp-2831_correction_events.parquet").exists() else None

print(f"Patients: {grid['patient_id'].nunique()}")
print(f"State assignments: {len(state)}")
print(f"Canonical EGP: {len(canonical_egp)}")

# ── H1: between-patient %State1 vs canonical EGP ─────────────────────────
print("\n── H1: %State1 vs canonical EGP (between patients) ──")
state_pct = state.groupby('patient_id')['state'].apply(lambda x: (x == 1).mean()).reset_index()
state_pct.columns = ['patient_id', 'pct_state1']
egp_pct = state_pct.merge(canonical_egp[['patient_id', 'canonical_egp_mg_dL_hr']], on='patient_id')
egp_pct = egp_pct.dropna(subset=['canonical_egp_mg_dL_hr'])
print(f"  patients with both: {len(egp_pct)}")

if len(egp_pct) >= 5:
    rho_h1, p_h1 = sp_stats.spearmanr(egp_pct['pct_state1'], egp_pct['canonical_egp_mg_dL_hr'])
    print(f"  Spearman ρ = {rho_h1:+.3f} (p = {p_h1:.3f})")
    for _, row in egp_pct.sort_values('canonical_egp_mg_dL_hr').iterrows():
        print(f"    {row['patient_id']:<25} pct_state1={row['pct_state1']*100:5.1f}%  EGP={row['canonical_egp_mg_dL_hr']:.1f}")
else:
    rho_h1, p_h1 = np.nan, np.nan

# ── State assignment → grid rows ─────────────────────────────────────────
state_sel = state[['patient_id', 'time', 'state']].copy()
state_sel['time'] = pd.to_datetime(state_sel['time'], utc=True)
state_sel = state_sel.sort_values('time').reset_index(drop=True)

grid['time'] = pd.to_datetime(grid['time'], utc=True)
grid = grid.sort_values('time').reset_index(drop=True)
grid_st = pd.merge_asof(
    grid, state_sel,
    on='time', by='patient_id',
    direction='backward',
    tolerance=pd.Timedelta('48h'),
)

# ── H2: within-patient EGP by state ──────────────────────────────────────
# EGP estimate via fasting flat-window method (equivalent to EXP-2739)
# A "fasting flat window" = 1h+ since last bolus AND last carb, low |ROC|,
# scheduled basal active. EGP_proxy ≈ -BG_drift / hour - basal × ISF
# But ISF varies, so use simpler method: when BG is FLAT and stable, the
# net (basal - EGP) ≈ 0, so EGP ≈ basal × scheduled_isf_hourly.
# We simply compare per-state mean basal × ISF in flat windows.

def state_egp_proxy(pdata, state_label):
    sub = pdata[(pdata['state'] == state_label) &
                (pdata['time_since_bolus_min'] >= 60) &
                (pdata['time_since_carb_min'] >= 120) &
                (pdata['glucose_roc'].abs() < 0.5)]  # flat
    if len(sub) < 10:
        return None
    # EGP proxy = basal_rate × scheduled_ISF (hourly mg/dL/hr)
    # i.e., the rate at which basal lowers BG = the rate at which EGP must
    # be raising it for BG to be flat.
    ev = (sub['actual_basal_rate'] * sub['scheduled_isf']).dropna()
    if len(ev) < 10:
        return None
    return {
        'n': int(len(ev)),
        'median': float(ev.median()),
        'mean': float(ev.mean()),
        'q25': float(ev.quantile(0.25)),
        'q75': float(ev.quantile(0.75)),
    }

print("\n── H2: per-state EGP estimates (within patient) ──")
print(f"{'patient':<25} {'state0_n':>8} {'state0_egp':>10} {'state1_n':>8} {'state1_egp':>10} {'ratio':>6}")
per_state_results = []
qualified = 0
for pid, pdata in grid_st.groupby('patient_id'):
    s0 = state_egp_proxy(pdata, 0)
    s1 = state_egp_proxy(pdata, 1)
    if s0 and s1 and s0['n'] >= 3 and s1['n'] >= 3:
        qualified += 1
        ratio = s1['median'] / s0['median'] if s0['median'] > 0 else np.nan
        per_state_results.append({
            'patient_id': pid,
            'state0_n': s0['n'], 'state0_egp': s0['median'],
            'state1_n': s1['n'], 'state1_egp': s1['median'],
            'ratio': ratio,
        })
        print(f"{pid:<25} {s0['n']:>8} {s0['median']:>10.1f} {s1['n']:>8} {s1['median']:>10.1f} {ratio:>6.2f}")

print(f"\n  Qualified patients (≥3 flat windows in each state): {qualified}")

if per_state_results:
    psr = pd.DataFrame(per_state_results)
    median_ratio = psr['ratio'].median()
    n_higher_in_s1 = (psr['ratio'] > 1.0).sum()
    print(f"  Median EGP_S1 / EGP_S0 = {median_ratio:.2f}")
    print(f"  Patients with EGP_S1 > EGP_S0: {n_higher_in_s1}/{len(psr)}")
    # Wilcoxon signed-rank
    if len(psr) >= 5:
        try:
            stat, p_h2 = sp_stats.wilcoxon(psr['state1_egp'], psr['state0_egp'])
            print(f"  Wilcoxon p={p_h2:.4f} (state1 vs state0)")
        except Exception as e:
            p_h2 = np.nan
            print(f"  Wilcoxon failed: {e}")
    else:
        p_h2 = np.nan
else:
    psr = pd.DataFrame()
    median_ratio, n_higher_in_s1, p_h2 = np.nan, 0, np.nan

# ── P5: state-stratified vs static EGP for ISF residual variance ─────────
print("\n── P5: state-stratified vs static EGP for residual variance ──")
if events is not None and len(per_state_results) >= 3:
    # Build per-patient state-EGP map
    psr_map = {row['patient_id']: {0: row['state0_egp'], 1: row['state1_egp']}
               for _, row in psr.iterrows()}
    static_egp = dict(zip(canonical_egp['patient_id'], canonical_egp['canonical_egp_mg_dL_hr']))

    ev = events.copy()
    ev['time'] = pd.to_datetime(ev['time'], utc=True)
    ev = ev.sort_values('time').reset_index(drop=True)
    ev = pd.merge_asof(ev, state_sel, on='time', by='patient_id',
                       direction='backward', tolerance=pd.Timedelta('48h'))

    def state_egp(row):
        pmap = psr_map.get(row['patient_id'])
        if not pmap or pd.isna(row['state']):
            return np.nan
        return pmap.get(int(row['state']), np.nan)

    ev['egp_static'] = ev['patient_id'].map(static_egp)
    ev['egp_state'] = ev.apply(state_egp, axis=1)
    ev_both = ev.dropna(subset=['egp_static', 'egp_state', 'isf_full']).copy()
    print(f"  events with both static and state-specific EGP: {len(ev_both)}")

    if len(ev_both) >= 30:
        # Within-patient demean
        ev_both['isf_dm'] = ev_both['isf_full'] - ev_both.groupby('patient_id')['isf_full'].transform('mean')
        ev_both['burden_static'] = ev_both['egp_static'] * 3.0 / ev_both['dose']
        ev_both['burden_state'] = ev_both['egp_state'] * 3.0 / ev_both['dose']
        ev_both['burden_static_dm'] = ev_both['burden_static'] - ev_both.groupby('patient_id')['burden_static'].transform('mean')
        ev_both['burden_state_dm'] = ev_both['burden_state'] - ev_both.groupby('patient_id')['burden_state'].transform('mean')

        # Univariate fits
        slope_s, _, r_static, p_static, _ = sp_stats.linregress(ev_both['burden_static_dm'], ev_both['isf_dm'])
        slope_st, _, r_state, p_state, _ = sp_stats.linregress(ev_both['burden_state_dm'], ev_both['isf_dm'])

        print(f"  Static EGP burden:    r={r_static:+.3f}  p={p_static:.4f}  R²={r_static**2*100:.1f}%")
        print(f"  State-stratified EGP: r={r_state:+.3f}  p={p_state:.4f}  R²={r_state**2*100:.1f}%")
        var_improvement = (r_state**2 - r_static**2) * 100
        print(f"  ΔR² (state - static): {var_improvement:+.2f}pp")
    else:
        var_improvement = 0
else:
    var_improvement = 0
    print("  insufficient events / per-state results")

# ── Success criteria ──────────────────────────────────────────────────────
results = {
    'experiment_id': EXP_ID,
    'title': TITLE,
    'date': datetime.now().isoformat(),
    'h1_rho': float(rho_h1) if not pd.isna(rho_h1) else None,
    'h1_p': float(p_h1) if not pd.isna(p_h1) else None,
    'h1_n': int(len(egp_pct)),
    'h2_qualified_patients': int(qualified),
    'h2_median_ratio': float(median_ratio) if not pd.isna(median_ratio) else None,
    'h2_n_higher_in_state1': int(n_higher_in_s1),
    'h2_wilcoxon_p': float(p_h2) if not pd.isna(p_h2) else None,
    'state_egp_var_improvement_pp': float(var_improvement),
    'criteria': {
        'P1_h1_rho_above_0.4': bool(abs(rho_h1) > 0.4) if not pd.isna(rho_h1) else False,
        'P2_5plus_patients_with_both_states': bool(qualified >= 5),
        'P3_median_ratio_above_1': bool(median_ratio > 1.0) if not pd.isna(median_ratio) else False,
        'P4_wilcoxon_significant': bool(p_h2 < 0.05) if not pd.isna(p_h2) else False,
        'P5_state_egp_improves_R2': bool(var_improvement > 0),
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
with open(out_dir / f"exp-{EXP_ID}_egp_state_interaction.json", 'w') as f:
    json.dump(results, f, indent=2, default=str)
if len(psr):
    psr.to_parquet(out_dir / f"exp-{EXP_ID}_per_state_egp.parquet")
print(f"\nSaved: exp-{EXP_ID}_egp_state_interaction.json")
