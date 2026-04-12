#!/usr/bin/env python3
"""EXP-2585: Correction-Based ISF Calibration with Counter-Regulation.

Hypotheses:
  H1: Per-patient counter-reg k enables accurate ISF calibration from corrections
      (optimal ISF multiplier within [0.8, 1.2] for most patients)
  H2: Correction-derived ISF differs systematically from meal-derived ISF
      (the ISF×0.5 artifact is meal-specific, corrections give ISF closer to 1.0)
  H3: Correction-based ISF calibration predicts actual correction outcomes
      better than the 0.78 dampening heuristic

Design:
  Phase 1: For each patient, use their calibrated k to sweep ISF multiplier
           on correction events. Find optimal ISF mult that minimizes MAE
           between simulated and actual glucose drops.
  Phase 2: Compare correction-optimal ISF vs meal-optimal ISF (from EXP-2568/2580)
  Phase 3: Validate correction-ISF predictions on held-out corrections (50/50 split)

This experiment aims to productionize the dual ISF pathway into settings_advisor.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cgmencode.production.forward_simulator import forward_simulate, TherapySettings, InsulinEvent

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
OUTFILE = Path("externals/experiments/exp-2585_correction_isf.json")

# Per-patient optimal k from EXP-2582 (NS) and EXP-2584 (ODC)
PATIENT_K = {
    "a": 2.0, "b": 3.0, "c": 7.0, "d": 1.5, "e": 1.5,
    "f": 1.0, "g": 1.0, "h": 0.0, "i": 3.0, "j": 0.0, "k": 0.0,
    "odc-74077367": 2.5, "odc-86025410": 0.5, "odc-96254963": 2.0,
}

ISF_GRID = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 2.0]
SIM_HOURS = 2.0
SIM_STEPS = int(SIM_HOURS * 12)
MIN_CORRECTIONS = 20

# Meal-optimal ISF from EXP-2568 (without counter-reg)
MEAL_ISF = {
    "a": 0.5, "b": 0.5, "c": 0.5, "d": 0.5, "e": 0.5,
    "f": 0.5, "g": 0.5, "h": 0.7, "i": 0.5, "j": 0.9, "k": 0.5,
}


def _extract_corrections(pdf: pd.DataFrame) -> list:
    """Extract correction bolus events with 2h glucose windows."""
    g = pdf["glucose"].values
    b = pdf["bolus"].values
    t = pd.to_datetime(pdf["time"])
    h = (t.dt.hour + t.dt.minute / 60.0).values
    carbs = pdf["carbs"].fillna(0).values
    iob = pdf["iob"].fillna(0).values
    isf = pdf["scheduled_isf"].values
    cr = pdf["scheduled_cr"].values
    basal_col = "scheduled_basal_rate" if "scheduled_basal_rate" in pdf.columns else "scheduled_basal"
    basal = pdf[basal_col].values

    N = len(g)
    corrections = []
    for i in range(N - SIM_STEPS):
        if b[i] < 0.5 or g[i] < 150 or carbs[i] > 1.0:
            continue
        if np.isnan(g[i]) or np.isnan(isf[i]) or np.isnan(cr[i]) or np.isnan(basal[i]):
            continue
        window_g = g[i : i + SIM_STEPS]
        valid = np.sum(~np.isnan(window_g))
        if valid < SIM_STEPS * 0.6:
            continue
        actual_end = np.nanmean(window_g[-3:])
        if np.isnan(actual_end):
            continue
        actual_drop = actual_end - g[i]

        corrections.append({
            "g0": float(g[i]),
            "bolus": float(b[i]),
            "iob": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
            "hour": float(h[i]),
            "isf": float(isf[i]),
            "cr": float(cr[i]),
            "basal": float(basal[i]),
            "actual_drop": float(actual_drop),
        })
    return corrections


def _sim_correction(c: dict, k: float, isf_mult: float = 1.0) -> float:
    """Simulate a correction with counter-reg and ISF multiplier."""
    s = TherapySettings(
        isf=c["isf"] * isf_mult,
        cr=c["cr"],
        basal_rate=c["basal"],
        dia_hours=5.0,
    )
    r = forward_simulate(
        initial_glucose=c["g0"],
        settings=s,
        duration_hours=SIM_HOURS,
        start_hour=c["hour"],
        bolus_events=[InsulinEvent(0, c["bolus"])],
        carb_events=[],
        initial_iob=c["iob"],
        noise_std=0,
        seed=42,
        counter_reg_k=k,
    )
    return r.glucose[-1] - c["g0"]


def run():
    df = pd.read_parquet(PARQUET)
    results = {"experiment": "EXP-2585", "patients": {}}

    all_patients = sorted(PATIENT_K.keys())
    for pid in all_patients:
        pdf = df[df["patient_id"] == pid].sort_values("time")
        if len(pdf) == 0:
            continue

        k = PATIENT_K[pid]
        corrections = _extract_corrections(pdf)
        if len(corrections) < MIN_CORRECTIONS:
            print(f"{pid}: {len(corrections)} corrections — SKIP")
            continue

        print(f"\n{'='*60}")
        print(f"Patient {pid}: {len(corrections)} corrections, k={k}")

        # Split corrections 50/50 for train/validate
        np.random.seed(42)
        idx = np.random.permutation(len(corrections))
        train_idx = idx[: len(idx) // 2]
        val_idx = idx[len(idx) // 2 :]
        train = [corrections[i] for i in train_idx]
        val = [corrections[i] for i in val_idx]

        # Phase 1: Sweep ISF multiplier on TRAINING corrections
        isf_results = []
        for isf_m in ISF_GRID:
            drops = []
            for c in train:
                sim_drop = _sim_correction(c, k=k, isf_mult=isf_m)
                drops.append({"sim": sim_drop, "actual": c["actual_drop"]})

            sim_d = np.array([d["sim"] for d in drops])
            act_d = np.array([d["actual"] for d in drops])
            valid = (~np.isnan(sim_d)) & (~np.isnan(act_d)) & (sim_d != 0)
            if valid.sum() < 5:
                continue
            ratio = float(np.mean(act_d[valid] / sim_d[valid]))
            mae = float(np.mean(np.abs(act_d[valid] - sim_d[valid])))
            isf_results.append({"isf_mult": isf_m, "ratio": round(ratio, 3), "mae": round(mae, 1)})

        best_by_ratio = min(isf_results, key=lambda x: abs(x["ratio"] - 1.0))
        best_by_mae = min(isf_results, key=lambda x: x["mae"])
        print(f"  Train: best ISF by ratio={best_by_ratio['isf_mult']}"
              f" (ratio={best_by_ratio['ratio']}, MAE={best_by_ratio['mae']})")
        print(f"  Train: best ISF by MAE={best_by_mae['isf_mult']}"
              f" (ratio={best_by_mae['ratio']}, MAE={best_by_mae['mae']})")

        # Phase 3: Validate on held-out corrections
        # Compare: (a) profile ISF (mult=1.0), (b) correction-optimal, (c) 0.78 dampened
        comparisons = {}
        for label, isf_m in [
            ("profile_1.0", 1.0),
            ("correction_optimal", best_by_mae["isf_mult"]),
            ("dampened_0.78", 0.78),
        ]:
            drops = []
            for c in val:
                sim_drop = _sim_correction(c, k=k, isf_mult=isf_m)
                drops.append({"sim": sim_drop, "actual": c["actual_drop"]})
            sim_d = np.array([d["sim"] for d in drops])
            act_d = np.array([d["actual"] for d in drops])
            valid = (~np.isnan(sim_d)) & (~np.isnan(act_d)) & (sim_d != 0)
            if valid.sum() > 0:
                ratio = float(np.mean(act_d[valid] / sim_d[valid]))
                mae = float(np.mean(np.abs(act_d[valid] - sim_d[valid])))
            else:
                ratio, mae = float("nan"), float("nan")
            comparisons[label] = {"ratio": round(ratio, 3), "mae": round(mae, 1)}
            print(f"  Val ({label}): ratio={ratio:.3f}, MAE={mae:.1f}")

        # Phase 2: Compare with meal-derived ISF
        meal_isf = MEAL_ISF.get(pid, None)

        patient_result = {
            "n_corrections": len(corrections),
            "k": k,
            "train_isf_sweep": isf_results,
            "best_isf_by_ratio": best_by_ratio["isf_mult"],
            "best_isf_by_mae": best_by_mae["isf_mult"],
            "validation": comparisons,
            "meal_optimal_isf": meal_isf,
        }
        results["patients"][pid] = patient_result

    # Summary analysis
    print(f"\n{'='*60}")
    print("SUMMARY")
    corr_isf_vals = []
    meal_isf_vals = []
    for pid, r in results["patients"].items():
        corr_isf = r["best_isf_by_mae"]
        meal_isf = r.get("meal_optimal_isf")
        corr_isf_vals.append(corr_isf)
        print(f"  {pid}: correction ISF×{corr_isf}, meal ISF×{meal_isf or 'N/A'}")
        if meal_isf is not None:
            meal_isf_vals.append(meal_isf)

    print(f"\n  Correction ISF: mean={np.mean(corr_isf_vals):.2f}, "
          f"median={np.median(corr_isf_vals):.2f}")
    if meal_isf_vals:
        print(f"  Meal ISF: mean={np.mean(meal_isf_vals):.2f}, "
              f"median={np.median(meal_isf_vals):.2f}")
        print(f"  Correction vs Meal difference: "
              f"{np.mean(corr_isf_vals[:len(meal_isf_vals)]) - np.mean(meal_isf_vals):.2f}")

    # Validation: does correction-optimal beat 0.78 dampened?
    corr_wins = 0
    damp_wins = 0
    for pid, r in results["patients"].items():
        v = r["validation"]
        corr_mae = v["correction_optimal"]["mae"]
        damp_mae = v["dampened_0.78"]["mae"]
        if corr_mae < damp_mae:
            corr_wins += 1
        else:
            damp_wins += 1
    total = corr_wins + damp_wins
    print(f"\n  H3: Correction-optimal beats 0.78 dampened: {corr_wins}/{total} patients")

    results["summary"] = {
        "mean_correction_isf": round(float(np.mean(corr_isf_vals)), 2),
        "median_correction_isf": round(float(np.median(corr_isf_vals)), 2),
        "mean_meal_isf": round(float(np.mean(meal_isf_vals)), 2) if meal_isf_vals else None,
        "correction_beats_dampened": f"{corr_wins}/{total}",
    }

    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    run()
