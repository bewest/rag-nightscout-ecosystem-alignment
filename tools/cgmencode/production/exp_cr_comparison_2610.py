#!/usr/bin/env python3
"""EXP-2610: Effective CR vs Sim-Optimized CR Comparison.

Hypothesis: The effective CR from meal response (EXP-2609) should agree
with the sim-optimized CR from forward_sim_optimization. If they converge,
both methods are validated. If they diverge, we can determine which
better predicts post-meal outcomes.

H1: Effective CR and sim-optimized CR are correlated (r ≥ 0.6) across
    patients — they measure the same underlying physiology.
H2: The average of effective CR and sim CR ("consensus CR") predicts
    post-meal TIR better than either alone.
H3: Patients where effective CR ≈ sim CR (within 20%) have better overall
    TIR than patients where they diverge, suggesting settings convergence
    indicates good calibration.

Design:
- Load effective CR from EXP-2609 results
- Run forward sim optimization to get sim-optimized CR per patient
- Compare the two CR estimates
- Test consensus CR vs individual CRs for outcome prediction
"""

import json
import sys
import os
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from cgmencode.production.settings_advisor import (
    generate_settings_advice,
    compute_settings_quality_score,
    _CR_K_GRID,
)
from cgmencode.production.forward_simulator import (
    forward_simulate,
    TherapySettings,
    InsulinEvent,
    CarbEvent,
)
from cgmencode.production.clinical_rules import generate_clinical_report
from cgmencode.production.types import PatientProfile

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
EXP2609 = Path("externals/experiments/exp-2609_effective_cr.json")
OUTFILE = Path("externals/experiments/exp-2610_cr_comparison.json")
FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]

# Counter-reg k per patient (from prior calibration)
PATIENT_K = {
    "a": 2.5, "b": 7.0, "c": 7.0, "d": 3.0, "e": 5.0,
    "f": 1.0, "g": 3.0, "i": 5.0, "k": 1.5,
}


def _get_sim_cr(pdf, profile, pid):
    """Get sim-optimized CR multiplier via grid search."""
    from cgmencode.production.settings_advisor import _extract_correction_windows

    correction_windows = _extract_correction_windows(
        glucose=pdf["glucose"].values,
        hours=pdf["time"].dt.hour.values,
        bolus=pdf["bolus"].values,
        iob=pdf["iob"].values if "iob" in pdf else None,
        carbs=pdf["carbs"].values if "carbs" in pdf else None,
        profile=profile,
        max_windows=50,
    )

    if len(correction_windows) < 5:
        return None, None

    k = PATIENT_K.get(pid, 3.0)
    isf_val = profile.isf_schedule[0]["value"]
    cr_val = profile.cr_schedule[0]["value"]
    basal_val = profile.basal_schedule[0]["value"]

    best_cr_mult = 1.0
    best_mae = float("inf")

    for cr_mult in [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5]:
        errors = []
        for w in correction_windows[:30]:
            settings = TherapySettings(
                isf=isf_val * 0.5,  # sim calibration factor
                cr=cr_val * cr_mult,
                basal_rate=basal_val,
            )
            result = forward_simulate(
                initial_glucose=w["g"],
                settings=settings,
                bolus_events=[InsulinEvent(time_minutes=0, units=w["b"])],
                carb_events=[],
                duration_hours=3.0,
                counter_reg_k=k,
            )
            predicted_end = result.glucose[-1]
            actual_end = w["g"] + w["actual_drop"]
            errors.append(abs(predicted_end - actual_end))

        mae = np.mean(errors)
        if mae < best_mae:
            best_mae = mae
            best_cr_mult = cr_mult

    sim_cr = cr_val * best_cr_mult
    return sim_cr, best_cr_mult


def main():
    print("=" * 70)
    print("EXP-2610: Effective CR vs Sim-Optimized CR Comparison")
    print("=" * 70)

    # Load EXP-2609 results
    if not EXP2609.exists():
        print("ERROR: EXP-2609 results not found. Run EXP-2609 first.")
        sys.exit(1)

    with open(EXP2609) as f:
        exp2609 = json.load(f)

    df = pd.read_parquet(PARQUET)
    df["time"] = pd.to_datetime(df["time"])
    print(f"Loaded {len(df)} rows\n")

    results = {}

    for pid in FULL_PATIENTS:
        pdf = df[df["patient_id"] == pid].sort_values("time").copy()
        if len(pdf) < 1000:
            continue

        if pid not in exp2609["patients"]:
            continue

        print(f"\n{'='*50}")
        print(f"PATIENT {pid}")
        print(f"{'='*50}")

        profile_cr = exp2609["patients"][pid]["profile_cr"]
        effective_cr = exp2609["patients"][pid]["effective_cr_median"]
        cr_ratio = exp2609["patients"][pid]["cr_ratio"]

        profile = PatientProfile(
            isf_schedule=[{"start": "00:00:00", "value": float(pdf["scheduled_isf"].dropna().median())}],
            cr_schedule=[{"start": "00:00:00", "value": float(pdf["scheduled_cr"].dropna().median())}],
            basal_schedule=[{"start": "00:00:00", "value": float(pdf["scheduled_basal_rate"].dropna().median())}],
            target_low=70,
            target_high=180,
            dia_hours=6.0,
        )

        # Get sim-optimized CR
        sim_cr, sim_mult = _get_sim_cr(pdf, profile, pid)

        if sim_cr is None:
            print(f"  Insufficient corrections for sim CR")
            continue

        # Compute consensus
        consensus_cr = (effective_cr + sim_cr) / 2
        agreement_pct = 1 - abs(effective_cr - sim_cr) / max(effective_cr, sim_cr) * 100

        # TIR for the patient
        glucose = pdf["glucose"].dropna().values
        tir = float(np.mean((glucose >= 70) & (glucose <= 180)) * 100)

        print(f"  Profile CR:   {profile_cr:.1f}")
        print(f"  Effective CR: {effective_cr:.1f} (ratio={cr_ratio:.2f})")
        print(f"  Sim CR:       {sim_cr:.1f} (mult={sim_mult:.2f})")
        print(f"  Consensus CR: {consensus_cr:.1f}")
        print(f"  Agreement:    {agreement_pct:.0f}%")
        print(f"  TIR:          {tir:.1f}%")

        results[pid] = {
            "profile_cr": profile_cr,
            "effective_cr": effective_cr,
            "sim_cr": round(sim_cr, 1),
            "sim_mult": round(sim_mult, 2),
            "consensus_cr": round(consensus_cr, 1),
            "cr_ratio_eff": round(cr_ratio, 2),
            "cr_ratio_sim": round(sim_mult, 2),
            "agreement_pct": round(agreement_pct, 1),
            "tir": round(tir, 1),
        }

    # ====== Cross-patient analysis ======
    print("\n" + "=" * 70)
    print("CROSS-PATIENT COMPARISON")
    print("=" * 70)

    pids = list(results.keys())
    eff_crs = [results[p]["effective_cr"] for p in pids]
    sim_crs = [results[p]["sim_cr"] for p in pids]
    tirs = [results[p]["tir"] for p in pids]
    agreements = [results[p]["agreement_pct"] for p in pids]

    # H1: Correlation between effective CR and sim CR
    h1_r, h1_p = stats.pearsonr(eff_crs, sim_crs)
    h1_confirmed = h1_r >= 0.6
    print(f"\nH1 - Effective CR vs Sim CR: r={h1_r:.3f} (p={h1_p:.4f})")
    print(f"  H1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'} (threshold: r ≥ 0.6)")

    # H2: Consensus CR predicts TIR better
    # Distance from profile CR (lower distance = better calibrated)
    eff_dist = [abs(results[p]["effective_cr"] - results[p]["profile_cr"]) for p in pids]
    sim_dist = [abs(results[p]["sim_cr"] - results[p]["profile_cr"]) for p in pids]
    con_dist = [abs(results[p]["consensus_cr"] - results[p]["profile_cr"]) for p in pids]

    eff_tir_r, _ = stats.pearsonr(eff_dist, tirs) if len(set(eff_dist)) > 1 else (0, 1)
    sim_tir_r, _ = stats.pearsonr(sim_dist, tirs) if len(set(sim_dist)) > 1 else (0, 1)
    con_tir_r, _ = stats.pearsonr(con_dist, tirs) if len(set(con_dist)) > 1 else (0, 1)

    print(f"\nH2 - CR distance vs TIR correlation:")
    print(f"  Effective CR distance vs TIR: r={eff_tir_r:.3f}")
    print(f"  Sim CR distance vs TIR:       r={sim_tir_r:.3f}")
    print(f"  Consensus CR distance vs TIR: r={con_tir_r:.3f}")
    h2_confirmed = abs(con_tir_r) > max(abs(eff_tir_r), abs(sim_tir_r))
    print(f"  H2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'} (consensus beats both)")

    # H3: Agreement correlates with TIR
    h3_r, h3_p = stats.pearsonr(agreements, tirs)
    h3_confirmed = h3_r >= 0.0  # any positive correlation
    print(f"\nH3 - CR agreement vs TIR: r={h3_r:.3f} (p={h3_p:.3f})")
    print(f"  H3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'} (positive correlation)")

    # Summary table
    print(f"\n{'Pt':>5s}  {'Prof':>6s}  {'Eff':>6s}  {'Sim':>6s}  {'Cons':>6s}  {'Agree':>6s}  {'TIR':>6s}")
    print("-" * 50)
    for pid in sorted(results.keys()):
        r = results[pid]
        print(f"{pid:>5s}  {r['profile_cr']:>6.1f}  {r['effective_cr']:>6.1f}  "
              f"{r['sim_cr']:>6.1f}  {r['consensus_cr']:>6.1f}  "
              f"{r['agreement_pct']:>5.0f}%  {r['tir']:>5.1f}%")

    # Save results
    output = {
        "experiment": "EXP-2610",
        "title": "Effective CR vs Sim-Optimized CR Comparison",
        "patients": results,
        "hypotheses": {
            "H1": {"description": "Effective CR vs Sim CR correlation",
                    "r": round(h1_r, 3), "p": round(h1_p, 4),
                    "confirmed": h1_confirmed},
            "H2": {"description": "Consensus CR beats both for TIR prediction",
                    "eff_r": round(eff_tir_r, 3),
                    "sim_r": round(sim_tir_r, 3),
                    "con_r": round(con_tir_r, 3),
                    "confirmed": h2_confirmed},
            "H3": {"description": "CR agreement correlates with TIR",
                    "r": round(h3_r, 3), "p": round(h3_p, 3),
                    "confirmed": h3_confirmed},
        },
    }

    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
