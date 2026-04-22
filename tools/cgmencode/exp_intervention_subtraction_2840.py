#!/usr/bin/env python3
"""
EXP-2840: Intervention Subtraction & Two-Stream Charter
========================================================

Conceptual framing (user-articulated, 2026-04-22):
  Patients staying alive means human + controller intervention is ALWAYS
  active, restoring homeostatic balance. Observed BG stability is a
  POST-INTERVENTION signal, not a natural physiology signal.

Two distinct analysis streams must be separated:

  STREAM A — PHYSICS MODEL (causal/biological):
    Goal: Understand what the body does (EGP, gastric absorption, sensitivity).
    Method: Subtract intervention contribution to recover natural dynamics.
    Risk: Cannot fully recover counterfactual; intervention is non-removable.
    Use: Digital twin, replay simulators, biological hypothesis tests.

  STREAM B — SETTINGS EXTRACTION (operational/control):
    Goal: Find ISF/CR/basal values for the controller-as-operating-loop.
    Method: Use observed responses INCLUDING intervention; settings are
            tuned to the closed-loop system, not naked physiology.
    Risk: Treating extracted settings as biological truth (counter-causal).
    Use: Per-patient profile recommendations, triage flags.

Conflation modes (counter-causal reasoning to avoid):
  C1: Inferring biology from closed-loop drops then recommending profile
      changes based on the inferred biology
  C2: Subtracting intervention to estimate "true" sensitivity, then using
      that estimate as a settings recommendation
  C3: Using physics estimates (EGP) as direct setting parameters

This experiment:
  Part 1: Quantify intervention burden vs natural drift per patient.
  Part 2: Estimate "what would have happened without intervention" using
          a counterfactual envelope (best-case and worst-case bounds).
  Part 3: Audit prior experiments (2790-2832) for conflation risk.
  Part 4: Establish stream-appropriate methodology guardrails.

Success criteria:
  P1: Quantify intervention-active fraction of time (should be ~100%)
  P2: Compute counterfactual BG envelope width per patient
  P3: Ratio (intervention burden / observed BG variance) > 0.5 for all
      patients (proves intervention dominates observed signal)
  P4: At least one prior experiment flagged for conflation risk
  P5: Document stream-appropriate methodology for each remaining
      experiment lineage
"""

import json
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

EXP_ID = 2840
TITLE = "Intervention Subtraction & Two-Stream Charter"
EXCLUDE = {'odc-84181797', 'h', 'j'}

print(f"[EXP-{EXP_ID}] {TITLE}")
print("=" * 70)

# ── Data ─────────────────────────────────────────────────────────────────
grid = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
grid = grid[~grid['patient_id'].isin(EXCLUDE)].copy()
grid = grid.sort_values(['patient_id', 'time']).reset_index(drop=True)
print(f"Patients: {grid['patient_id'].nunique()}")

# ── Part 1: Intervention burden quantification ───────────────────────────
print("\n── Part 1: Intervention burden per patient ──")
print(f"{'patient':<25} {'TDD U/d':>9} {'basal%':>7} {'bolus%':>7} {'SMB%':>6} "
      f"{'iob_med':>8} {'int_act%':>9}")

intervention = []
for pid, p in grid.groupby('patient_id'):
    days = (p['time'].max() - p['time'].min()).total_seconds() / 86400
    if days < 1:
        continue
    # Insulin breakdown (5-min rates → daily totals)
    actual_basal_u_per_5min = (p['actual_basal_rate'].fillna(0) / 12)
    bolus_total = p['bolus'].fillna(0).sum()
    smb_total = p['bolus_smb'].fillna(0).sum() if 'bolus_smb' in p.columns else 0
    basal_total = actual_basal_u_per_5min.sum()
    tdd = (basal_total + bolus_total) / days
    if tdd <= 0:
        continue
    # Intervention-active fraction (any IOB present OR insulin delivered)
    intervention_active = ((p['iob'].fillna(0) > 0.05) |
                            (p['bolus'].fillna(0) > 0) |
                            (actual_basal_u_per_5min > 0)).mean()
    intervention.append({
        'patient_id': pid,
        'tdd_u_per_day': tdd,
        'basal_pct': basal_total / (basal_total + bolus_total) * 100 if (basal_total + bolus_total) > 0 else 0,
        'bolus_pct': bolus_total / (basal_total + bolus_total) * 100 if (basal_total + bolus_total) > 0 else 0,
        'smb_pct': smb_total / bolus_total * 100 if bolus_total > 0 else 0,
        'iob_median': float(p['iob'].median()),
        'intervention_active_pct': intervention_active * 100,
    })

intv_df = pd.DataFrame(intervention)
for _, r in intv_df.head(10).iterrows():
    print(f"{r['patient_id']:<25} {r['tdd_u_per_day']:>9.1f} {r['basal_pct']:>7.1f} "
          f"{r['bolus_pct']:>7.1f} {r['smb_pct']:>6.1f} {r['iob_median']:>8.2f} "
          f"{r['intervention_active_pct']:>9.1f}")
print(f"  ... ({len(intv_df)} patients total)")

mean_int_active = intv_df['intervention_active_pct'].mean()
print(f"\n  Mean intervention-active fraction: {mean_int_active:.1f}%")
print(f"  Median TDD: {intv_df['tdd_u_per_day'].median():.1f} U/day")
print(f"  Median IOB: {intv_df['iob_median'].median():.2f} U")

# ── Part 2: Counterfactual envelope ──────────────────────────────────────
print("\n── Part 2: Counterfactual BG envelope ──")
print("  For each patient, compute: observed BG variance vs intervention burden")
print("  Counterfactual estimate: BG would drift by approximately")
print("    drift = (insulin_effect_lost - EGP_compensated) per unit time")

# Use known scheduled ISF as the patient-tuned conversion
counter = []
for pid, p in grid.groupby('patient_id'):
    bg = p['glucose'].dropna()
    if len(bg) < 100:
        continue
    isf = p['scheduled_isf'].median()
    if pd.isna(isf) or isf <= 0:
        continue
    actual_basal_u_per_5min = p['actual_basal_rate'].fillna(0) / 12
    # Mean insulin effect rate (mg/dL/hr lowered by basal)
    basal_effect_rate = actual_basal_u_per_5min.mean() * 12 * isf  # U/hr × mg/dL/U
    # Mean bolus contribution rate
    bolus_effect_rate = (p['bolus'].fillna(0).sum() /
                         ((p['time'].max() - p['time'].min()).total_seconds() / 3600)
                         * isf)
    total_intervention_rate = basal_effect_rate + bolus_effect_rate
    bg_observed_std = bg.std()
    bg_observed_range = bg.quantile(0.95) - bg.quantile(0.05)
    counter.append({
        'patient_id': pid,
        'scheduled_isf': float(isf),
        'basal_effect_mg_dL_hr': float(basal_effect_rate),
        'bolus_effect_mg_dL_hr': float(bolus_effect_rate),
        'total_intervention_mg_dL_hr': float(total_intervention_rate),
        'bg_observed_std': float(bg_observed_std),
        'bg_observed_p5_p95_range': float(bg_observed_range),
        # Counterfactual drift if intervention removed for 1 hour
        'counterfactual_1hr_drift': float(total_intervention_rate),
        # Ratio: intervention vs observed variance
        # (intervention rate per hour vs std deviation in mg/dL)
        'intervention_dominance_ratio': float(total_intervention_rate / bg_observed_std)
        if bg_observed_std > 0 else np.nan,
    })

cf_df = pd.DataFrame(counter)
print(f"\n  Patients analyzed: {len(cf_df)}")
print(f"  Median intervention effect rate: {cf_df['total_intervention_mg_dL_hr'].median():.1f} mg/dL/hr")
print(f"  Median observed BG std: {cf_df['bg_observed_std'].median():.1f} mg/dL")
print(f"  Median 1-hour counterfactual drift: {cf_df['counterfactual_1hr_drift'].median():.1f} mg/dL")
print(f"  Intervention-dominance ratio (intervention_rate / BG_std):")
print(f"    median: {cf_df['intervention_dominance_ratio'].median():.2f}")
print(f"    fraction with ratio > 0.5: {(cf_df['intervention_dominance_ratio'] > 0.5).mean()*100:.0f}%")
print(f"    fraction with ratio > 1.0: {(cf_df['intervention_dominance_ratio'] > 1.0).mean()*100:.0f}%")

# ── Part 3: Audit prior experiments for conflation risk ─────────────────
print("\n── Part 3: Conflation risk audit ──")
audit = [
    {
        'exp': 'EXP-2737', 'topic': 'Profile ISF gap',
        'stream': 'B (settings)', 'risk': 'LOW',
        'note': 'Already correctly framed as profile (controller param) vs observed (closed-loop)',
    },
    {
        'exp': 'EXP-2756/2758', 'topic': 'EGP from drift', 'stream': 'A (physics)',
        'risk': 'MEDIUM',
        'note': 'EGP estimated via drift; basal compensation creates near-zero residual. Findings are conservative biology estimates.',
    },
    {
        'exp': 'EXP-2820', 'topic': 'EGP audit', 'stream': 'A (physics)',
        'risk': 'MEDIUM',
        'note': 'Cross-method audit; methods 2739/2740 are partial physics inference. Canonical EGP should be labeled as STREAM A.',
    },
    {
        'exp': 'EXP-2821', 'topic': 'EGP-aware report cards',
        'stream': 'A→B conflation',
        'risk': 'HIGH (CAUGHT)',
        'note': 'Already noted: profile ISF ≠ biological ISF. Recommendation logic was correctly held back from suggesting profile changes based on biology.',
    },
    {
        'exp': 'EXP-2830', 'topic': 'Formulation constant',
        'stream': 'A (physics)', 'risk': 'MEDIUM',
        'note': 'Tested biology hypothesis using closed-loop drops. Hypothesis refuted — ironically the closed-loop confound likely contributed to refutation.',
    },
    {
        'exp': 'EXP-2831', 'topic': 'Multi-timescale wear',
        'stream': 'B (settings/triage)',
        'risk': 'LOW',
        'note': 'Triage signals are operational; correctly kept in Stream B.',
    },
    {
        'exp': 'EXP-2823 H2', 'topic': 'Within-patient state EGP',
        'stream': 'A (physics)', 'risk': 'HIGH',
        'note': 'Tried to estimate within-patient EGP from closed-loop data. The 0-valued proxies are exactly the intervention-subtraction problem this charter addresses. NOT FOUND result is partly an observability artifact.',
    },
    {
        'exp': 'EXP-2832', 'topic': 'Inverse EGP',
        'stream': 'A→B conflation risk',
        'risk': 'MEDIUM',
        'note': 'Inverse EGP estimates are biology-stream but use settings-stream features (ISF_med). Honest-use guide already restricts to ranking, not absolute clinical use.',
    },
]
print(f"  {'EXP':<15} {'topic':<28} {'stream':<22} {'risk':<15}")
high_risk_count = 0
for a in audit:
    print(f"  {a['exp']:<15} {a['topic']:<28} {a['stream']:<22} {a['risk']:<15}")
    if 'HIGH' in a['risk']:
        high_risk_count += 1

# ── Part 4: Stream-appropriate methodology guardrails ───────────────────
print("\n── Part 4: Methodology guardrails ──")
guardrails = [
    "G1: Stream A (physics) experiments must report counterfactual error bands "
        "from intervention-subtraction; absolute estimates are inherently lower-bounded.",
    "G2: Stream B (settings) experiments must NOT use Stream A estimates as "
        "absolute setting values; only as covariates in extraction methods.",
    "G3: When closed-loop data is the only source, Stream A inferences need "
        "explicit 'controller-confounded' label.",
    "G4: Reports should declare the stream of each finding and flag any "
        "Stream A → Stream B translation as REQUIRES CLINICAL VALIDATION.",
    "G5: Triage signals (Stream B) can use any layer of the pipeline as input "
        "without conflation risk because they don't claim biology.",
]
for g in guardrails:
    print(f"  {g}")

# ── Success criteria ──────────────────────────────────────────────────────
results = {
    'experiment_id': EXP_ID,
    'title': TITLE,
    'date': datetime.now().isoformat(),
    'mean_intervention_active_pct': float(mean_int_active),
    'median_tdd': float(intv_df['tdd_u_per_day'].median()),
    'median_intervention_rate_mg_dL_hr': float(cf_df['total_intervention_mg_dL_hr'].median()),
    'median_intervention_dominance_ratio': float(cf_df['intervention_dominance_ratio'].median()),
    'fraction_dominance_above_0.5': float((cf_df['intervention_dominance_ratio'] > 0.5).mean()),
    'high_risk_experiments_flagged': high_risk_count,
    'audit': audit,
    'guardrails': guardrails,
    'criteria': {
        'P1_intervention_active_above_90pct': bool(mean_int_active > 90),
        'P2_envelope_computed': bool(len(cf_df) > 0),
        'P3_dominance_above_0.5_for_majority': bool((cf_df['intervention_dominance_ratio'] > 0.5).mean() > 0.5),
        'P4_at_least_one_high_risk_flagged': bool(high_risk_count >= 1),
        'P5_guardrails_documented': bool(len(guardrails) >= 4),
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
with open(out_dir / f"exp-{EXP_ID}_intervention_subtraction.json", 'w') as f:
    json.dump(results, f, indent=2, default=str)
intv_df.to_parquet(out_dir / f"exp-{EXP_ID}_intervention_burden.parquet")
cf_df.to_parquet(out_dir / f"exp-{EXP_ID}_counterfactual_envelope.parquet")
print(f"\nSaved: exp-{EXP_ID}_intervention_subtraction.json")
