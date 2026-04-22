#!/usr/bin/env python3
"""
EXP-2831: Multi-Timescale Supply/Demand with Wear Effects
==========================================================

User framing (supply/demand metaphor):
  SUPPLY (slow, ~2-3 day timescale):
    EGP (steady + meals) + resistance loss
  DEMAND (fast, ~6h timescale):
    IOB over time (basal + bolus + SMB) + sensitivity loss
  WEAR (mid-timescale):
    - Sensor: warmup → mid-life accuracy → end-of-life staleness
    - Infusion site: fresh → aged → degraded delivery (apparent resistance)

Multi-layer architecture (to isolate setting parameters from confounds):
  Layer 0: Raw observed ISF (drop / dose)
  Layer 1: Subtract slow-supply (state/EGP regime — Lines A, B)
  Layer 2: Subtract wear (sensor age, cannula age)
  Layer 3: Residual = "clean" sensitivity signal for setting extraction

Actionable triage outputs (translatable to override suggestions):
  - High cage_hours + apparent resistance → "consider site change"
  - High sage_hours + drift → "sensor stale, recalibrate"
  - Sustained State 1 → "consider temporary -10% ISF profile"

Method:
  1. Use correction events from EXP-2830
  2. Annotate each event with: state (EXP-2810), egp (EXP-2820),
     sage_hours, cage_hours at event start
  3. Stratify ISF by quintile of each wear factor
  4. Multi-factor regression: ISF ~ K + β_state + β_cage + β_sage + β_egp_burden
  5. Compare variance reduction at each layer

Success criteria:
  P1: At least one wear factor shows monotonic ISF effect (sage or cage)
  P2: Multi-factor model explains >25% more variance than raw
  P3: ≥2 of 4 factors are statistically significant (p<0.05)
  P4: At least 1 patient has actionable triage signal
      (e.g., cage>48h cohort shows ISF reduction >20%)
  P5: Stratified ISF (after wear correction) has lower CV than raw
"""

import json
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats as sp_stats
from sklearn.linear_model import LinearRegression

warnings.filterwarnings('ignore')

EXP_ID = 2831
TITLE = "Multi-Timescale Supply/Demand with Wear Effects"
EXCLUDE = {'odc-84181797', 'h', 'j'}

print(f"[EXP-{EXP_ID}] {TITLE}")
print("=" * 70)

# ── Data ─────────────────────────────────────────────────────────────────
events = pd.read_parquet("externals/experiments/exp-2830_correction_events.parquet")
grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
grid = grid[~grid['patient_id'].isin(EXCLUDE)].copy()
grid = grid.sort_values(['patient_id', 'time']).reset_index(drop=True)
state_assign = pd.read_parquet("externals/experiments/exp-2810_state_assignments.parquet")
canonical_egp = pd.read_parquet("externals/experiments/exp-2820_canonical_egp.parquet")

print(f"Events from EXP-2830: {len(events)}")
print(f"State assignments: {len(state_assign)}")

# ── Re-extract events with WEAR annotations ──────────────────────────────
# Need to re-attach wear factors at event timestamps; events parquet doesn't
# have time, so we re-derive by index matching using bg_start within patient.
# Simpler: re-extract from grid with wear columns.
def extract_with_wear(pdata):
    pdata = pdata.sort_values('time').reset_index(drop=True)
    bg = pdata['glucose'].values
    bolus = pdata['bolus'].fillna(0).values
    carbs = pdata['carbs'].fillna(0).values
    iob = pdata['iob'].fillna(0).values
    cage = pdata['cage_hours'].values
    sage = pdata['sage_hours'].values
    swarmup = pdata['sensor_warmup'].fillna(0).values
    noise = pdata['rolling_noise'].values
    times = pdata['time'].values
    n = len(pdata)
    out = []
    for i in range(72, n - 42):
        if bolus[i] < 0.5 or bg[i] < 180:
            continue
        if carbs[max(0, i - 36):min(n, i + 36)].sum() > 5:
            continue
        if iob[i] > 2.0:
            continue
        back = bg[max(0, i - 72):i]
        if np.isnan(back).any():
            continue
        time_in_high = (back > 180).sum() / 12.0
        if not (1 <= time_in_high <= 6):
            continue
        fwd = bg[i:i + 42]
        if np.isnan(fwd).any():
            continue
        # Skip during sensor warmup
        if swarmup[i] > 0.5:
            continue
        drop_full = bg[i] - np.min(fwd)
        if drop_full <= 0:
            continue
        out.append({
            'time': times[i],
            'bg_start': float(bg[i]),
            'dose': float(bolus[i]),
            'drop_full': float(drop_full),
            'isf_full': float(drop_full / bolus[i]),
            'cage_hours': float(cage[i]) if not np.isnan(cage[i]) else np.nan,
            'sage_hours': float(sage[i]) if not np.isnan(sage[i]) else np.nan,
            'rolling_noise': float(noise[i]) if not np.isnan(noise[i]) else np.nan,
        })
    return out

print("\n── Re-extracting with wear annotations ──")
all_events = []
for pid in sorted(grid['patient_id'].unique()):
    pdata = grid[grid['patient_id'] == pid]
    evs = extract_with_wear(pdata)
    for e in evs:
        e['patient_id'] = pid
    all_events.extend(evs)

ev = pd.DataFrame(all_events)
print(f"  {len(ev)} events with wear data, {ev['patient_id'].nunique()} patients")
print(f"  cage_hours coverage: {ev['cage_hours'].notna().sum()}")
print(f"  sage_hours coverage: {ev['sage_hours'].notna().sum()}")

# ── Attach state ─────────────────────────────────────────────────────────
# ── Attach state ─────────────────────────────────────────────────────────
state_sel = state_assign[['patient_id', 'time', 'state']].copy()
state_sel['time'] = pd.to_datetime(state_sel['time'], utc=True)
state_sel = state_sel.sort_values('time').reset_index(drop=True)
ev['time'] = pd.to_datetime(ev['time'], utc=True)
ev = ev.sort_values('time').reset_index(drop=True)
ev_with_state = pd.merge_asof(
    ev, state_sel,
    on='time', by='patient_id',
    direction='backward',
    tolerance=pd.Timedelta('48h'),
)
print(f"  state coverage: {ev_with_state['state'].notna().sum()}")

# ── Attach EGP ───────────────────────────────────────────────────────────
egp_lookup = dict(zip(canonical_egp['patient_id'], canonical_egp['canonical_egp_mg_dL_hr']))
ev_with_state['egp'] = ev_with_state['patient_id'].map(egp_lookup)
ev_with_state['egp_burden'] = ev_with_state['egp'] * 3.0 / ev_with_state['dose']

ef = ev_with_state.copy()

# ── Layer 0: raw ─────────────────────────────────────────────────────────
print("\n── Layer 0: Raw ISF ──")
raw_pat = ef.groupby('patient_id')['isf_full'].median()
raw_cv = raw_pat.std() / raw_pat.mean()
print(f"  population mean: {raw_pat.mean():.1f}, inter-patient CV: {raw_cv:.3f}")

# ── Wear stratification ──────────────────────────────────────────────────
print("\n── Wear stratification ──")

def quintile_strat(df, col, label):
    sub = df[df[col].notna()].copy()
    if len(sub) < 50:
        print(f"  {label}: too few events")
        return None
    sub['q'] = pd.qcut(sub[col], q=5, labels=False, duplicates='drop')
    grp = sub.groupby('q').agg(
        n=('isf_full', 'count'),
        col_med=(col, 'median'),
        isf_med=('isf_full', 'median'),
        isf_mean=('isf_full', 'mean'),
    )
    print(f"  {label}:")
    for q, row in grp.iterrows():
        print(f"    Q{int(q)}: {col}={row['col_med']:>6.1f}  n={int(row['n']):>4}  "
              f"ISF_med={row['isf_med']:>6.1f}  ISF_mean={row['isf_mean']:>6.1f}")
    # Monotonicity test: spearman of quintile vs ISF
    rho, p = sp_stats.spearmanr(grp.index, grp['isf_med'])
    print(f"    monotonicity ρ={rho:+.3f} (p={p:.3f})")
    return {'rho': float(rho), 'p': float(p),
            'q0_isf': float(grp['isf_med'].iloc[0]),
            'q4_isf': float(grp['isf_med'].iloc[-1]),
            'effect_pct': float((grp['isf_med'].iloc[-1] - grp['isf_med'].iloc[0]) /
                                grp['isf_med'].iloc[0] * 100)}

cage_strat = quintile_strat(ef, 'cage_hours', 'CAGE (cannula age)')
sage_strat = quintile_strat(ef, 'sage_hours', 'SAGE (sensor age)')
noise_strat = quintile_strat(ef, 'rolling_noise', 'Rolling noise')

# State stratification
print(f"\n  STATE (slow timescale, EXP-2810):")
for s, sub in ef.dropna(subset=['state']).groupby('state'):
    print(f"    State {int(s)}: n={len(sub)}  ISF_med={sub['isf_full'].median():.1f}")

# ── Multi-factor regression ──────────────────────────────────────────────
print("\n── Multi-factor regression ──")
# Build feature matrix: state, cage, sage, noise, egp_burden, patient FE
# Use within-patient demeaning to absorb patient-level variation
features = ['cage_hours', 'sage_hours', 'rolling_noise', 'state', 'egp_burden']
ef_clean = ef.dropna(subset=features + ['isf_full']).copy()
print(f"  Events with all features: {len(ef_clean)} from {ef_clean['patient_id'].nunique()} patients")

# Within-patient demeaning to remove patient FE
ef_clean['isf_demeaned'] = ef_clean['isf_full'] - ef_clean.groupby('patient_id')['isf_full'].transform('mean')
for f in features:
    ef_clean[f'{f}_dm'] = ef_clean[f] - ef_clean.groupby('patient_id')[f].transform('mean')

X_cols = [f'{f}_dm' for f in features]
X = ef_clean[X_cols].values
y = ef_clean['isf_demeaned'].values
reg = LinearRegression().fit(X, y)
y_pred = reg.predict(X)
r2 = 1 - np.var(y - y_pred) / np.var(y)
print(f"\n  Within-patient model R²: {r2*100:.1f}%")
print(f"  {'feature':<20} {'coef':>10} {'|effect at 1σ|':>15}")
for f, c in zip(features, reg.coef_):
    sigma = ef_clean[f].std()
    print(f"  {f:<20} {c:>10.3f} {abs(c) * sigma:>15.2f} mg/dL/U")

# Per-feature significance via individual regression on demeaned target
print(f"\n  Univariate t-tests (demeaned):")
sig_count = 0
sig_results = {}
for f in features:
    Xi = ef_clean[[f'{f}_dm']].values
    if Xi.std() < 1e-6:
        continue
    slope, intercept, r, p, se = sp_stats.linregress(Xi.ravel(), y)
    print(f"    {f:<20}: β={slope:+.4f}  r={r:+.3f}  p={p:.4f}")
    sig_results[f] = {'slope': float(slope), 'r': float(r), 'p': float(p)}
    if p < 0.05:
        sig_count += 1

# ── Layer 3: residual after wear+state correction ───────────────────────
print("\n── Layer 3: After multi-factor correction ──")
ef_clean['isf_corrected'] = ef_clean['isf_full'] - y_pred + ef_clean.groupby('patient_id')['isf_full'].transform('mean')
# Note: subtracting within-patient predictions removes wear/state/EGP signal
# while preserving patient mean
corr_pat = ef_clean.groupby('patient_id')['isf_corrected'].median()
corr_cv = corr_pat.std() / corr_pat.mean()
print(f"  population mean: {corr_pat.mean():.1f}, inter-patient CV: {corr_cv:.3f}")
print(f"  CV change: {(corr_cv - raw_cv) / raw_cv * 100:+.1f}%")

# Within-patient CV reduction
print(f"\n  Within-patient CV reduction:")
intra_raw = ef_clean.groupby('patient_id')['isf_full'].std() / ef_clean.groupby('patient_id')['isf_full'].mean()
intra_corr = ef_clean.groupby('patient_id')['isf_corrected'].std() / ef_clean.groupby('patient_id')['isf_corrected'].mean()
print(f"    median intra-patient CV (raw):       {intra_raw.median():.3f}")
print(f"    median intra-patient CV (corrected): {intra_corr.median():.3f}")
intra_cv_reduction = (intra_raw.median() - intra_corr.median()) / intra_raw.median() * 100
print(f"    reduction: {intra_cv_reduction:+.1f}%")

# ── Actionable triage: per-patient cage threshold scan ──────────────────
print("\n── Actionable triage signals ──")
triage = []
for pid, sub in ef.dropna(subset=['cage_hours']).groupby('patient_id'):
    if len(sub) < 20:
        continue
    fresh = sub[sub['cage_hours'] < 24]
    aged = sub[sub['cage_hours'] >= 48]
    if len(fresh) < 5 or len(aged) < 5:
        continue
    isf_fresh = fresh['isf_full'].median()
    isf_aged = aged['isf_full'].median()
    delta_pct = (isf_aged - isf_fresh) / isf_fresh * 100
    triage.append({
        'patient_id': pid,
        'isf_fresh_site': float(isf_fresh),
        'isf_aged_site': float(isf_aged),
        'delta_pct': float(delta_pct),
        'n_fresh': int(len(fresh)),
        'n_aged': int(len(aged)),
        'flag_site_change': bool(delta_pct < -20),
    })

triage_df = pd.DataFrame(triage)
print(f"  {len(triage_df)} patients with both fresh and aged site events")
if len(triage_df):
    flagged = triage_df[triage_df['flag_site_change']]
    print(f"  {len(flagged)} patients flagged: aged-site ISF >20% lower than fresh")
    if len(flagged):
        print(f"    examples:")
        for _, row in flagged.head(5).iterrows():
            print(f"      {row['patient_id']}: fresh ISF={row['isf_fresh_site']:.1f}, "
                  f"aged ISF={row['isf_aged_site']:.1f} ({row['delta_pct']:+.0f}%)")

# ── Success criteria ──────────────────────────────────────────────────────
strats = {'cage': cage_strat, 'sage': sage_strat, 'noise': noise_strat}
monotonic_count = sum(1 for s in strats.values() if s and abs(s['rho']) >= 0.6)

results = {
    'experiment_id': EXP_ID,
    'title': TITLE,
    'date': datetime.now().isoformat(),
    'n_events_full': int(len(ef)),
    'n_events_complete': int(len(ef_clean)),
    'within_patient_R2_pct': float(r2 * 100),
    'wear_stratification': {k: v for k, v in strats.items() if v},
    'sig_count': int(sig_count),
    'univariate_results': sig_results,
    'inter_patient_cv_raw': float(raw_cv),
    'inter_patient_cv_corrected': float(corr_cv),
    'intra_patient_cv_reduction_pct': float(intra_cv_reduction),
    'n_patients_flagged_site_change': int(len(triage_df[triage_df['flag_site_change']])) if len(triage_df) else 0,
    'criteria': {
        'P1_wear_factor_monotonic': bool(monotonic_count >= 1),
        'P2_multifactor_R2_above_25': bool(r2 * 100 >= 25),
        'P3_two_features_significant': bool(sig_count >= 2),
        'P4_at_least_one_actionable_flag': bool(len(triage_df[triage_df['flag_site_change']]) >= 1) if len(triage_df) else False,
        'P5_intra_patient_cv_reduces': bool(intra_cv_reduction > 0),
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
with open(out_dir / f"exp-{EXP_ID}_multitimescale_wear.json", 'w') as f:
    json.dump(results, f, indent=2, default=str)
if len(triage_df):
    triage_df.to_parquet(out_dir / f"exp-{EXP_ID}_triage_flags.parquet")
print(f"\nSaved: exp-{EXP_ID}_multitimescale_wear.json")
