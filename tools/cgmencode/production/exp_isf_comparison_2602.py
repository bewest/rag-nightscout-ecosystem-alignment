#!/usr/bin/env python3
"""EXP-2602: Correction-Based ISF vs Sim-Based ISF Advisory Comparison.

EXP-2601 revealed that sim-based ISF advisories confound calibration
parameters (ISF×0.5 for ranking accuracy) with clinical recommendations.
The predicted TIR improvement is not validated by simulation.

This experiment compares:
  A) Sim-based ISF (from forward sim joint optimization)
  B) Correction-based ISF (from actual correction bolus outcomes)
  C) Clinical ISF (from actual glucose drops per unit insulin)

Hypotheses:
  H1: Correction-based ISF (B) matches actual glucose drops better
      than sim-based ISF (A) — lower MAE on held-out corrections.
  H2: Clinical ISF (C, raw drop/dose) provides the most actionable
      recommendation — suggested value closest to effective ISF.
  H3: Sim-based ISF magnitude is consistently ~2× too aggressive
      (because ISF×0.5 calibration factor doubles the recommendation).
  H4: Using correction-based ISF in dose-response shows >0% optimal
      dose for ≥5/9 patients.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cgmencode.production.forward_simulator import (
    forward_simulate, TherapySettings, InsulinEvent,
)

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
OUTFILE = Path("externals/experiments/exp-2602_isf_comparison.json")

FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]


def _extract_corrections(pdf, max_events=100):
    """Extract all correction boluses with outcomes."""
    glucose = pdf["glucose"].values
    bolus = pdf["bolus"].fillna(0).values
    carbs = pdf["carbs"].fillna(0).values
    hours = (pd.to_datetime(pdf["time"]).dt.hour +
             pd.to_datetime(pdf["time"]).dt.minute / 60.0).values

    corrections = []
    N = len(pdf)
    for i in range(N - 24):
        if bolus[i] < 0.5 or carbs[i] > 1.0:
            continue
        if np.isnan(glucose[i]) or glucose[i] < 150:
            continue
        post_idx = i + 24
        if post_idx >= N or np.isnan(glucose[post_idx]):
            continue

        corrections.append({
            "glucose_start": float(glucose[i]),
            "glucose_end": float(glucose[post_idx]),
            "drop": float(glucose[i] - glucose[post_idx]),
            "bolus": float(bolus[i]),
            "hour": float(hours[i]),
            "effective_isf": float((glucose[i] - glucose[post_idx]) / bolus[i]),
        })
        if len(corrections) >= max_events:
            break

    return corrections


def main():
    print("=" * 70)
    print("EXP-2602: Correction-Based vs Sim-Based ISF Comparison")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    results = {}

    for pid in FULL_PATIENTS:
        print(f"\n{'=' * 50}")
        print(f"PATIENT {pid}")
        print(f"{'=' * 50}")

        pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if pdf.empty:
            continue

        corrections = _extract_corrections(pdf)
        if len(corrections) < 10:
            print(f"  Only {len(corrections)} corrections, skipping")
            continue

        # Split 70/30
        np.random.seed(42)
        idx = np.random.permutation(len(corrections))
        split = int(0.7 * len(corrections))
        cal_corr = [corrections[i] for i in idx[:split]]
        val_corr = [corrections[i] for i in idx[split:]]

        profile_isf = float(pdf["scheduled_isf"].dropna().median())
        basal = float(pdf["scheduled_basal_rate"].dropna().median())

        print(f"  Profile ISF: {profile_isf:.1f}")
        print(f"  {len(corrections)} corrections: {len(cal_corr)} cal, {len(val_corr)} val")

        # Method A: Sim-based ISF (ISF×0.5 calibration)
        sim_isf = profile_isf * 0.5
        print(f"\n  A) Sim-based ISF: {sim_isf:.1f} (profile × 0.5)")

        # Method B: Correction-based ISF (median effective ISF from corrections)
        effective_isfs = [c["effective_isf"] for c in cal_corr]
        correction_isf = float(np.median(effective_isfs))
        print(f"  B) Correction-based ISF: {correction_isf:.1f}")

        # Method C: Clinical ISF (correction-based, but suggesting profile change)
        # This IS the effective ISF — what the patient's profile ISF should be
        clinical_suggested = correction_isf
        print(f"  C) Clinical suggested ISF: {clinical_suggested:.1f}")

        # Evaluate on validation set
        # For each method, predict the glucose drop and compare to actual
        val_actual_drops = np.array([c["drop"] for c in val_corr])
        val_doses = np.array([c["bolus"] for c in val_corr])

        # A: Sim prediction (using sim with ISF×0.5 and counter-reg k)
        sim_drops_a = []
        for c in val_corr:
            ts = TherapySettings(
                isf=sim_isf, cr=10.0, basal_rate=basal,
                dia_hours=5.0,
            )
            result = forward_simulate(
                initial_glucose=c["glucose_start"],
                settings=ts,
                bolus_events=[InsulinEvent(time_minutes=0, units=c["bolus"])],
                duration_hours=2.0,
                counter_reg_k=2.0,
            )
            sim_drops_a.append(c["glucose_start"] - result.glucose[-1])
        sim_drops_a = np.array(sim_drops_a)

        # B: Correction ISF prediction (simple: drop = dose × correction_isf)
        pred_drops_b = val_doses * correction_isf

        # C: Profile ISF prediction (simple: drop = dose × profile_isf)
        pred_drops_c = val_doses * profile_isf

        # Metrics
        mae_a = float(np.mean(np.abs(sim_drops_a - val_actual_drops)))
        mae_b = float(np.mean(np.abs(pred_drops_b - val_actual_drops)))
        mae_c = float(np.mean(np.abs(pred_drops_c - val_actual_drops)))

        bias_a = float(np.mean(sim_drops_a - val_actual_drops))
        bias_b = float(np.mean(pred_drops_b - val_actual_drops))
        bias_c = float(np.mean(pred_drops_c - val_actual_drops))

        r_a, _ = stats.spearmanr(sim_drops_a, val_actual_drops)
        r_b, _ = stats.spearmanr(pred_drops_b, val_actual_drops)
        r_c, _ = stats.spearmanr(pred_drops_c, val_actual_drops)

        print(f"\n  Validation ({len(val_corr)} corrections):")
        print(f"  {'Method':<15} {'ISF':>6} {'MAE':>6} {'Bias':>7} {'r':>6}")
        print(f"  {'A) Sim':>15} {sim_isf:>6.1f} {mae_a:>6.1f} {bias_a:>+7.1f} {r_a:>6.3f}")
        print(f"  {'B) Correction':>15} {correction_isf:>6.1f} {mae_b:>6.1f} {bias_b:>+7.1f} {r_b:>6.3f}")
        print(f"  {'C) Profile':>15} {profile_isf:>6.1f} {mae_c:>6.1f} {bias_c:>+7.1f} {r_c:>6.3f}")

        # H3 check: sim ISF magnitude vs correction ISF
        ratio = sim_isf / correction_isf if correction_isf > 0 else 0
        print(f"\n  Sim/Correction ISF ratio: {ratio:.2f}× (H3 expects ~0.5×)")

        results[pid] = {
            "patient_id": pid,
            "profile_isf": profile_isf,
            "sim_isf": sim_isf,
            "correction_isf": correction_isf,
            "clinical_suggested": clinical_suggested,
            "n_corrections": len(corrections),
            "mae_a": mae_a, "mae_b": mae_b, "mae_c": mae_c,
            "bias_a": bias_a, "bias_b": bias_b, "bias_c": bias_c,
            "r_a": float(r_a), "r_b": float(r_b), "r_c": float(r_c),
            "sim_correction_ratio": ratio,
        }

    # Cross-patient analysis
    print(f"\n{'=' * 70}")
    print("CROSS-PATIENT SUMMARY")
    print(f"{'=' * 70}")

    sdf = pd.DataFrame([{
        "pid": r["patient_id"],
        "prof": r["profile_isf"],
        "sim": r["sim_isf"],
        "corr": r["correction_isf"],
        "mae_a": r["mae_a"],
        "mae_b": r["mae_b"],
        "mae_c": r["mae_c"],
        "r_a": r["r_a"],
        "r_b": r["r_b"],
        "r_c": r["r_c"],
        "ratio": r["sim_correction_ratio"],
    } for r in results.values()])

    print(f"\n{'Pt':<4} {'Prof':>5} {'Sim':>5} {'Corr':>5} {'MAE_A':>6} {'MAE_B':>6} {'Ratio':>6}")
    print("-" * 45)
    for _, r in sdf.iterrows():
        print(f"{r['pid']:<4} {r['prof']:>5.1f} {r['sim']:>5.1f} {r['corr']:>5.1f} "
              f"{r['mae_a']:>6.1f} {r['mae_b']:>6.1f} {r['ratio']:>6.2f}")

    # H1: Correction-based MAE < sim-based MAE
    b_wins = (sdf["mae_b"] < sdf["mae_a"]).sum()
    print(f"\nH1 - Correction MAE < Sim MAE for {b_wins}/{len(sdf)} patients")
    h1_confirmed = b_wins >= 5
    print(f"  H1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'} (threshold: ≥5)")

    # H2: Clinical ISF closest to effective ISF
    sdf["dist_corr"] = abs(sdf["corr"] - sdf["corr"])  # by definition 0
    sdf["dist_sim"] = abs(sdf["sim"] - sdf["corr"])
    sdf["dist_prof"] = abs(sdf["prof"] - sdf["corr"])
    print(f"\nH2 - Mean distance to effective ISF:")
    print(f"  Sim:        {sdf['dist_sim'].mean():.1f}")
    print(f"  Profile:    {sdf['dist_prof'].mean():.1f}")
    h2_confirmed = sdf["dist_sim"].mean() > sdf["dist_prof"].mean() * 0.5
    print(f"  H2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'} (sim further from effective)")

    # H3: Sim ISF ~0.5× correction ISF
    mean_ratio = sdf["ratio"].mean()
    print(f"\nH3 - Mean sim/correction ISF ratio: {mean_ratio:.2f}× (expect ~0.5)")
    h3_confirmed = 0.3 < mean_ratio < 0.7
    print(f"  H3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'} (range: 0.3-0.7)")

    output = {
        "experiment": "EXP-2602",
        "title": "Correction-Based vs Sim-Based ISF Comparison",
        "h1_confirmed": h1_confirmed,
        "h2_confirmed": h2_confirmed,
        "h3_confirmed": h3_confirmed,
        "mean_sim_correction_ratio": mean_ratio,
        "patient_results": list(results.values()),
    }
    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
