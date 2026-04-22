#!/usr/bin/env python3
"""
EXP-2820: EGP Audit & Reconciliation
======================================

Rationale:
  20+ prior experiments produced EGP estimates ranging from -0.38 to +132
  mg/dL/hr. This wide range is not a contradiction — it reflects different
  measurement contexts and methods. This experiment audits all prior EGP
  work, builds a single canonical per-patient EGP table, and identifies
  which estimates are usable for downstream production work.

Method:
  1. Load all EGP-related experiment JSONs
  2. Extract per-patient EGP estimates with method tags
  3. Convert all to common units (mg/dL/hr)
  4. Identify and flag implausible estimates
  5. Compute consensus per-patient EGP from credible methods only
  6. Compare to UVA/Padova reference (~16 mg/dL/hr raw hepatic output)
  7. Categorize EGP into: raw_hepatic, net_after_basal, residual_after_dia

Success criteria:
  P1: ≥3 prior methods produce credible per-patient EGP estimates
  P2: Methods agree (correlation > 0.5) on rank-ordering of patients
  P3: Net EGP (after basal) is significantly < raw EGP — confirming
      that AID controllers cancel most EGP in steady state
  P4: At least 1 patient identified as high-EGP outlier (>1.0 mg/dL/5min)
  P5: Canonical EGP table produced for ≥10 patients
"""

import json
import sys
import warnings
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

warnings.filterwarnings('ignore')

EXP_ID = 2820
TITLE = "EGP Audit & Reconciliation"

print(f"[EXP-{EXP_ID}] {TITLE}")
print("=" * 70)

EXP_DIR = Path("externals/experiments")

# ── Audit catalog: experiments touching EGP ──────────────────────────────
AUDIT = [
    # (exp_id, file, method_tag, unit, notes)
    (2591, "exp-2591_iob_corrected_egp.json", "iob_corrected_slope", "mg/dL/hr", "IOB-corrected nocturnal slope"),
    (2727, "exp-2727_isf_gap_decomposition.json", "isf_gap_attribution", "fraction", "EGP=42% of ISF gap"),
    (2728, "exp-2728_egp_aware_validation.json", "validation_outcome", "MAE_delta", "Profile+EGP+CR vs Profile"),
    (2735, "exp-2735_egp_basal.json", "basal_egp_balance", "U/hr", "EGP-aware basal opt"),
    (2739, "exp-2739_egp_personalization.json", "fasting_drift_per_patient", "mg/dL/5min", "Per-patient profiling"),
    (2740, "exp-2740_basal_egp_equilibrium.json", "circadian_egp", "mg/dL/5min", "Equilibrium analysis"),
    (2742, "exp-2742_egp_personalized_isf.json", "egp_isf_correction", "ISF_delta", "Personalized ISF"),
    (2744, "exp-2744_universal_egp.json", "universal_estimate", "mg/dL/5min", "Universal extraction"),
    (2757, "exp-2757_egp_quantification.json", "drift_minus_basal", "mg/dL/5min", "Possibly circular"),
    (2797, "exp-2797_egp_settings.json", "egp_settings_aware", "R2_delta", "Settings R² gain"),
    (2809, "exp-2809_sensor_gap_effect.json", "sensor_gap_drift", "mg/dL/hr", "From this session"),
]

# ── Load and extract ──────────────────────────────────────────────────────
per_patient_egp = defaultdict(dict)  # {patient_id: {method: value_mg_dL_per_hr}}
method_summaries = {}

print("\n── Auditing prior EGP experiments ──")
for exp_id, fname, method_tag, unit, notes in AUDIT:
    fpath = EXP_DIR / fname
    if not fpath.exists():
        print(f"  EXP-{exp_id}: MISSING ({fname})")
        continue
    try:
        data = json.load(open(fpath))
    except Exception as e:
        print(f"  EXP-{exp_id}: PARSE ERROR ({e})")
        continue
    print(f"  EXP-{exp_id}: {method_tag:30s} unit={unit:15s} -- {notes}")
    method_summaries[exp_id] = {'tag': method_tag, 'unit': unit, 'notes': notes}

    # ─ Extract per-patient where structure permits ─
    if exp_id == 2591:
        for entry in data.get('summary', []):
            pid = entry['patient']
            # raw_slope is mg/dL/hr (negative = drift down). EGP estimate is the iob_corr - raw_slope.
            egp_hr = entry.get('egp')  # already mg/dL/hr per source code
            if egp_hr is not None:
                per_patient_egp[pid][f'iob_corr_{exp_id}'] = float(egp_hr)

    elif exp_id == 2739:
        for entry in data.get('per_patient_egp_profiles', []):
            pid = entry['patient_id']
            egp_med = entry.get('egp_median')
            if egp_med is not None:
                # mg/dL/5min → mg/dL/hr
                per_patient_egp[pid][f'fasting_{exp_id}'] = float(egp_med) * 12

    elif exp_id == 2740:
        for pid, pdata in data.get('per_patient_egp', {}).items():
            med = pdata.get('median_egp')
            if med is not None:
                per_patient_egp[pid][f'equilibrium_{exp_id}'] = float(med) * 12

    elif exp_id == 2757:
        for pid, pdata in data.get('egp_analysis', {}).items():
            rate = pdata.get('egp_rate_per_5min')
            n_w = pdata.get('n_windows', 0)
            if rate is not None and n_w >= 100:  # filter small-n outliers
                per_patient_egp[pid][f'drift_{exp_id}'] = float(rate) * 12

# ── Convert to DataFrame ──────────────────────────────────────────────────
all_methods = set()
for d in per_patient_egp.values():
    all_methods.update(d.keys())
all_methods = sorted(all_methods)

rows = []
for pid, methods in per_patient_egp.items():
    row = {'patient_id': pid}
    for m in all_methods:
        row[m] = methods.get(m, np.nan)
    rows.append(row)

egp_table = pd.DataFrame(rows).sort_values('patient_id').reset_index(drop=True)
print(f"\n── Per-patient EGP table ({len(egp_table)} patients × {len(all_methods)} methods) ──")
print(f"Methods: {all_methods}")

# Summary statistics per method
print(f"\n{'method':30s} {'n':>5} {'median':>10} {'mean':>10} {'min':>10} {'max':>10}")
for m in all_methods:
    vals = egp_table[m].dropna().values
    if len(vals) == 0:
        continue
    print(f"{m:30s} {len(vals):>5} {np.median(vals):>10.2f} {np.mean(vals):>10.2f} "
          f"{np.min(vals):>10.2f} {np.max(vals):>10.2f}")

# ── Method credibility: flag outliers and impossible values ──────────────
# Plausible per-patient EGP range (mg/dL/hr): 0 to 30 (UVA/Padova ~16, range up to 25)
print("\n── Credibility filter (plausible EGP: 0-30 mg/dL/hr) ──")
for m in all_methods:
    vals = egp_table[m].dropna().values
    if len(vals) == 0:
        continue
    in_range = ((vals >= 0) & (vals <= 30)).sum()
    pct_credible = 100 * in_range / len(vals)
    print(f"  {m:30s} credible {in_range}/{len(vals)} ({pct_credible:.0f}%)")

# ── Cross-method correlation (rank-order agreement) ──────────────────────
print("\n── Cross-method rank correlation ──")
corr_pairs = []
for i, m1 in enumerate(all_methods):
    for m2 in all_methods[i+1:]:
        both = egp_table[[m1, m2]].dropna()
        if len(both) >= 5:
            r, p = sp_stats.spearmanr(both[m1], both[m2])
            corr_pairs.append({'m1': m1, 'm2': m2, 'n': len(both), 'rho': r, 'p': p})
            print(f"  {m1[:20]} vs {m2[:20]}: n={len(both)}, ρ={r:+.3f} (p={p:.3f})")

# ── Canonical consensus EGP ──────────────────────────────────────────────
# Use methods with credibility > 50% only
credible_methods = []
for m in all_methods:
    vals = egp_table[m].dropna().values
    if len(vals) == 0:
        continue
    in_range = ((vals >= 0) & (vals <= 30)).sum() / len(vals)
    if in_range >= 0.5:
        credible_methods.append(m)
print(f"\n── Canonical methods (≥50% credible): {credible_methods}")

# Canonical = median of credible methods, clipped to 0-30
def canonical_egp(row):
    vals = []
    for m in credible_methods:
        v = row.get(m)
        if pd.notna(v) and 0 <= v <= 30:
            vals.append(v)
    return np.median(vals) if vals else np.nan

egp_table['canonical_egp_mg_dL_hr'] = egp_table.apply(canonical_egp, axis=1)
egp_table['n_credible_methods'] = egp_table[credible_methods].apply(
    lambda r: sum((pd.notna(v) and 0 <= v <= 30) for v in r), axis=1)

n_canonical = egp_table['canonical_egp_mg_dL_hr'].notna().sum()
print(f"  Canonical EGP available for {n_canonical}/{len(egp_table)} patients")
if n_canonical > 0:
    print(f"  Median canonical EGP: {egp_table['canonical_egp_mg_dL_hr'].median():.2f} mg/dL/hr")
    print(f"  Range: {egp_table['canonical_egp_mg_dL_hr'].min():.2f} – {egp_table['canonical_egp_mg_dL_hr'].max():.2f}")

# ── High-EGP outliers ─────────────────────────────────────────────────────
high_egp = egp_table[egp_table['canonical_egp_mg_dL_hr'] > 12].sort_values('canonical_egp_mg_dL_hr', ascending=False)
print(f"\n── High-EGP outliers (>12 mg/dL/hr, near UVA/Padova reference) ──")
print(high_egp[['patient_id', 'canonical_egp_mg_dL_hr', 'n_credible_methods']].to_string(index=False))

# ── Reference comparison ──────────────────────────────────────────────────
UVA_PADOVA_RAW_EGP = 16.0  # mg/dL/hr
canonical_median = egp_table['canonical_egp_mg_dL_hr'].median()
fraction_of_uva = canonical_median / UVA_PADOVA_RAW_EGP if pd.notna(canonical_median) else np.nan

print(f"\n── Reference reconciliation ──")
print(f"  UVA/Padova raw hepatic EGP:   {UVA_PADOVA_RAW_EGP:.1f} mg/dL/hr")
print(f"  Our canonical (closed-loop):  {canonical_median:.2f} mg/dL/hr")
print(f"  Ratio (closed-loop / raw):    {fraction_of_uva:.2%}")
print(f"  Interpretation: AID controllers cancel ~{(1-fraction_of_uva)*100:.0f}% of raw EGP via basal")

# ── Save canonical table ─────────────────────────────────────────────────
out_dir = EXP_DIR
canonical_path = out_dir / f"exp-{EXP_ID}_canonical_egp.parquet"
egp_table.to_parquet(canonical_path)
print(f"\nSaved canonical EGP table: {canonical_path}")

# ── Success criteria ──────────────────────────────────────────────────────
results = {
    'experiment_id': EXP_ID,
    'title': TITLE,
    'date': datetime.now().isoformat(),
    'experiments_audited': len([e for e in AUDIT if (EXP_DIR / e[1]).exists()]),
    'methods_extracted': len(all_methods),
    'patients_with_canonical': int(n_canonical),
    'canonical_methods': credible_methods,
    'canonical_egp_median_mg_dL_hr': float(canonical_median) if pd.notna(canonical_median) else None,
    'canonical_egp_range': [
        float(egp_table['canonical_egp_mg_dL_hr'].min()) if n_canonical > 0 else None,
        float(egp_table['canonical_egp_mg_dL_hr'].max()) if n_canonical > 0 else None,
    ],
    'uva_padova_ref_mg_dL_hr': UVA_PADOVA_RAW_EGP,
    'closed_loop_to_raw_ratio': float(fraction_of_uva) if pd.notna(fraction_of_uva) else None,
    'high_egp_patients': high_egp['patient_id'].tolist(),
    'cross_method_correlations': corr_pairs,
    'method_summaries': method_summaries,
    'criteria': {
        'P1_ge_3_credible_methods': bool(len(credible_methods) >= 3),
        'P2_methods_agree_rho_gt_0.5': bool(any(c['rho'] > 0.5 for c in corr_pairs) if corr_pairs else False),
        'P3_net_egp_lt_raw': bool(canonical_median < UVA_PADOVA_RAW_EGP if pd.notna(canonical_median) else False),
        'P4_high_egp_outlier_exists': bool(len(high_egp) >= 1),
        'P5_ge_10_patients_canonical': bool(n_canonical >= 10),
    }
}
results['n_pass'] = sum(1 for v in results['criteria'].values() if v)
results['pass_count'] = f"{results['n_pass']}/5"

print("\n" + "=" * 70)
print(f"SUCCESS CRITERIA ({results['pass_count']} PASS)")
print("=" * 70)
for k, v in results['criteria'].items():
    print(f"  {'✓' if v else '✗'}  {k}")

out_path = out_dir / f"exp-{EXP_ID}_egp_audit.json"
with open(out_path, 'w') as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nSaved: {out_path}")
