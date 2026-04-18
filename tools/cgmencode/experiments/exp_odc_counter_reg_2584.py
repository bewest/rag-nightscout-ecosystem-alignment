#!/usr/bin/env python3
"""EXP-2584: ODC Cohort Counter-Regulation + Sensitivity Ratio Analysis.

Hypotheses:
  H1: Counter-reg k calibration works on ODC patients (correction ratio→[0.7, 1.3])
  H2: Using effective_ISF = scheduled_ISF × sensitivity_ratio reduces sim error
  H3: With sensitivity_ratio correction, optimal ISF multiplier is closer to 1.0

Design:
  Phase 1: Calibrate per-patient k on ODC patients with ≥50 corrections
           (odc-74077367, odc-86025410, odc-96254963)
  Phase 2: For patients with sensitivity_ratio (74077367, 96254963),
           run correction sim with ISF × sens_ratio vs ISF alone
  Phase 3: Joint ISF×CR optimization on ODC with counter-reg
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cgmencode.production.forward_simulator import forward_simulate, TherapySettings, InsulinEvent, CarbEvent

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
OUTFILE = Path("externals/experiments/exp-2584_odc_counter_reg.json")

# ODC patients with enough corrections
ODC_PATIENTS = ["odc-74077367", "odc-86025410", "odc-96254963"]
K_GRID = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.0, 10.0]
SIM_HOURS = 2.0
SIM_STEPS = int(SIM_HOURS * 12)
MIN_CORRECTIONS = 20


def _extract_corrections(pdf: pd.DataFrame) -> list:
    """Extract correction bolus events with 2h glucose windows."""
    g = pdf["glucose"].values
    b = pdf["bolus"].values
    # Derive fractional hours from time column
    t = pd.to_datetime(pdf["time"])
    h = (t.dt.hour + t.dt.minute / 60.0).values
    carbs = pdf["carbs"].fillna(0).values
    iob = pdf["iob"].fillna(0).values
    isf = pdf["scheduled_isf"].values
    cr = pdf["scheduled_cr"].values
    basal_col = "scheduled_basal_rate" if "scheduled_basal_rate" in pdf.columns else "scheduled_basal"
    basal = pdf[basal_col].values
    sens = pdf["sensitivity_ratio"].values if "sensitivity_ratio" in pdf.columns else np.full(len(pdf), np.nan)

    N = len(g)
    corrections = []
    for i in range(N - SIM_STEPS):
        if b[i] < 0.5 or g[i] < 150 or carbs[i] > 1.0:
            continue
        if np.isnan(g[i]):
            continue
        window_g = g[i : i + SIM_STEPS]
        valid = np.sum(~np.isnan(window_g))
        if valid < SIM_STEPS * 0.6:
            continue
        actual_end = np.nanmean(window_g[-3:])
        if np.isnan(actual_end):
            continue
        actual_drop = actual_end - g[i]
        if np.isnan(isf[i]) or np.isnan(cr[i]) or np.isnan(basal[i]):
            continue

        corrections.append(
            {
                "g0": float(g[i]),
                "bolus": float(b[i]),
                "iob": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                "hour": float(h[i]),
                "isf": float(isf[i]),
                "cr": float(cr[i]),
                "basal": float(basal[i]),
                "sens_ratio": float(sens[i]) if not np.isnan(sens[i]) else None,
                "actual_drop": float(actual_drop),
                "actual_end": float(actual_end),
            }
        )
    return corrections


def _sim_correction(c: dict, k: float, use_sens_ratio: bool = False) -> float:
    """Simulate a correction event and return predicted drop."""
    isf = c["isf"]
    if use_sens_ratio and c["sens_ratio"] is not None:
        isf = isf * c["sens_ratio"]

    s = TherapySettings(
        isf=isf,
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
    results = {"experiment": "EXP-2584", "patients": {}}

    for pid in ODC_PATIENTS:
        pdf = df[df["patient_id"] == pid].sort_values("time")
        print(f"\n{'='*60}")
        print(f"Patient {pid}: {len(pdf):,} rows, {pdf['time'].dt.date.nunique()} days")

        corrections = _extract_corrections(pdf)
        print(f"  Corrections extracted: {len(corrections)}")
        if len(corrections) < MIN_CORRECTIONS:
            print(f"  SKIP: fewer than {MIN_CORRECTIONS} corrections")
            continue

        n_with_sens = sum(1 for c in corrections if c["sens_ratio"] is not None)
        print(f"  With sensitivity_ratio: {n_with_sens}/{len(corrections)}")

        # Phase 1: Per-patient k calibration (no sens_ratio)
        k_results = []
        for k in K_GRID:
            drops = []
            for c in corrections:
                sim_drop = _sim_correction(c, k=k, use_sens_ratio=False)
                drops.append({"sim": sim_drop, "actual": c["actual_drop"]})

            sim_drops = np.array([d["sim"] for d in drops])
            actual_drops = np.array([d["actual"] for d in drops])
            # Filter out NaN and zero values
            valid = (~np.isnan(sim_drops)) & (~np.isnan(actual_drops)) & (sim_drops != 0)
            if valid.sum() < 10:
                continue
            ratio = float(np.mean(actual_drops[valid] / sim_drops[valid]))
            mae = float(np.mean(np.abs(actual_drops[valid] - sim_drops[valid])))
            k_results.append({"k": k, "ratio": round(ratio, 3), "mae": round(mae, 1)})
            print(f"  k={k:.1f}: ratio={ratio:.3f}, MAE={mae:.1f}")

        # Find best k (closest ratio to 1.0)
        best_k_entry = min(k_results, key=lambda x: abs(x["ratio"] - 1.0))
        print(f"  → Best k: {best_k_entry['k']} (ratio={best_k_entry['ratio']})")

        # Phase 2: Sensitivity ratio analysis (if available)
        sens_results = None
        if n_with_sens >= 20:
            sens_corr = [c for c in corrections if c["sens_ratio"] is not None]
            print(f"\n  Phase 2: Sensitivity ratio analysis ({len(sens_corr)} corrections)")

            for use_sens in [False, True]:
                label = "with_sens" if use_sens else "no_sens"
                drops = []
                for c in sens_corr:
                    sim_drop = _sim_correction(c, k=best_k_entry["k"], use_sens_ratio=use_sens)
                    drops.append({"sim": sim_drop, "actual": c["actual_drop"]})
                sim_d = np.array([d["sim"] for d in drops])
                act_d = np.array([d["actual"] for d in drops])
                valid = (~np.isnan(sim_d)) & (~np.isnan(act_d)) & (sim_d != 0)
                ratio = float(np.mean(act_d[valid] / sim_d[valid])) if valid.sum() > 0 else float('nan')
                mae = float(np.mean(np.abs(act_d[valid] - sim_d[valid]))) if valid.sum() > 0 else float('nan')
                print(f"  {label}: ratio={ratio:.3f}, MAE={mae:.1f}")
                if sens_results is None:
                    sens_results = {}
                sens_results[label] = {"ratio": round(ratio, 3), "mae": round(mae, 1)}

            # Sensitivity ratio distribution
            sens_vals = [c["sens_ratio"] for c in sens_corr]
            print(f"  Sensitivity ratio stats: mean={np.mean(sens_vals):.3f}, "
                  f"std={np.std(sens_vals):.3f}, "
                  f"range=[{min(sens_vals):.2f}, {max(sens_vals):.2f}]")
            sens_results["stats"] = {
                "mean": round(float(np.mean(sens_vals)), 3),
                "std": round(float(np.std(sens_vals)), 3),
                "min": round(float(min(sens_vals)), 2),
                "max": round(float(max(sens_vals)), 2),
                "n": len(sens_vals),
            }

        # Phase 3: Joint ISF×CR optimization with counter-reg
        print(f"\n  Phase 3: Joint optimization (k={best_k_entry['k']})")
        ISF_GRID = [0.5, 0.7, 0.9, 1.0, 1.1, 1.3, 1.5, 2.0]
        CR_GRID = [1.0, 1.5, 2.0, 2.5, 3.0]

        # Extract meal windows for optimization
        g_arr = pdf["glucose"].values
        b_arr = pdf["bolus"].values
        c_arr = pdf["carbs"].fillna(0).values
        t_arr = pd.to_datetime(pdf["time"])
        h_arr = (t_arr.dt.hour + t_arr.dt.minute / 60.0).values
        iob_arr = pdf["iob"].fillna(0).values
        isf_arr = pdf["scheduled_isf"].values
        cr_arr = pdf["scheduled_cr"].values
        basal_col = "scheduled_basal_rate" if "scheduled_basal_rate" in pdf.columns else "scheduled_basal"
        basal_arr = pdf[basal_col].values
        N = len(g_arr)
        MEAL_STEPS = 48  # 4h

        meals = []
        for i in range(N - MEAL_STEPS):
            if c_arr[i] < 10 or b_arr[i] < 0.1:
                continue
            if np.isnan(g_arr[i]):
                continue
            wg = g_arr[i : i + MEAL_STEPS]
            if np.sum(np.isnan(wg)) > 5:
                continue
            meals.append({
                "g": float(g_arr[i]), "b": float(b_arr[i]),
                "c": float(c_arr[i]), "iob": float(iob_arr[i]) if not np.isnan(iob_arr[i]) else 0.0,
                "h": float(h_arr[i]),
                "isf": float(isf_arr[i]), "cr": float(cr_arr[i]),
                "basal": float(basal_arr[i]),
                "actual_glucose": [float(x) if not np.isnan(x) else None for x in wg],
            })
            if len(meals) >= 50:
                break

        print(f"  Meal windows: {len(meals)}")

        joint_results = {}
        if len(meals) >= 10:
            best_tir = -1
            best_isf_m, best_cr_m = 1.0, 1.0
            for isf_m in ISF_GRID:
                for cr_m in CR_GRID:
                    tirs = []
                    for m in meals:
                        try:
                            s = TherapySettings(
                                isf=m["isf"] * isf_m, cr=m["cr"] * cr_m,
                                basal_rate=m["basal"], dia_hours=5.0,
                            )
                            r = forward_simulate(
                                initial_glucose=m["g"], settings=s,
                                duration_hours=4.0, start_hour=m["h"],
                                bolus_events=[InsulinEvent(0, m["b"])],
                                carb_events=[CarbEvent(0, m["c"])],
                                initial_iob=m["iob"], noise_std=0, seed=42,
                                counter_reg_k=0.0,  # No counter-reg for meals
                            )
                            gluc = np.array(r.glucose)
                            tirs.append(float(np.mean((gluc >= 70) & (gluc <= 180))))
                        except Exception:
                            pass
                    if tirs:
                        mean_tir = float(np.mean(tirs))
                        if mean_tir > best_tir:
                            best_tir = mean_tir
                            best_isf_m = isf_m
                            best_cr_m = cr_m

            baseline_tir_val = None
            tirs_b = []
            for m in meals:
                try:
                    s = TherapySettings(
                        isf=m["isf"], cr=m["cr"], basal_rate=m["basal"], dia_hours=5.0,
                    )
                    r = forward_simulate(
                        initial_glucose=m["g"], settings=s,
                        duration_hours=4.0, start_hour=m["h"],
                        bolus_events=[InsulinEvent(0, m["b"])],
                        carb_events=[CarbEvent(0, m["c"])],
                        initial_iob=m["iob"], noise_std=0, seed=42,
                    )
                    gluc = np.array(r.glucose)
                    tirs_b.append(float(np.mean((gluc >= 70) & (gluc <= 180))))
                except Exception:
                    pass
            if tirs_b:
                baseline_tir_val = float(np.mean(tirs_b))

            print(f"  Best joint: ISF×{best_isf_m}, CR×{best_cr_m}, TIR={best_tir:.3f} "
                  f"(baseline={baseline_tir_val:.3f})")
            joint_results = {
                "best_isf": best_isf_m, "best_cr": best_cr_m,
                "best_tir": round(best_tir, 3),
                "baseline_tir": round(baseline_tir_val, 3) if baseline_tir_val else None,
                "n_meals": len(meals),
            }

        # TIR for this patient
        glucose_vals = pdf["glucose"].dropna().values
        tir = float(np.mean((glucose_vals >= 70) & (glucose_vals <= 180))) * 100

        results["patients"][pid] = {
            "n_rows": len(pdf),
            "n_days": int(pdf["time"].dt.date.nunique()),
            "tir": round(tir, 1),
            "n_corrections": len(corrections),
            "k_sweep": k_results,
            "best_k": best_k_entry["k"],
            "best_ratio": best_k_entry["ratio"],
            "sensitivity_ratio_analysis": sens_results,
            "joint_optimization": joint_results,
        }

    # Summary comparison with NS cohort
    ns_k = {"a": 2.0, "b": 3.0, "c": 7.0, "d": 1.5, "e": 1.5,
            "f": 1.0, "g": 1.0, "h": 0.0, "i": 3.0, "j": 0.0, "k": 0.0}
    ns_tir = {"a": 70.1, "b": 72.9, "c": 62.0, "d": 73.9, "e": 76.0,
              "f": 73.3, "g": 78.6, "h": 84.6, "i": 66.6, "j": 80.2, "k": 75.2}
    print(f"\n{'='*60}")
    print("CROSS-COHORT COMPARISON")
    print(f"  NS patients: median k={np.median(list(ns_k.values())):.1f}, "
          f"median TIR={np.median(list(ns_tir.values())):.1f}%")
    odc_ks = [r["best_k"] for r in results["patients"].values()]
    odc_tirs = [r["tir"] for r in results["patients"].values()]
    if odc_ks:
        print(f"  ODC patients: median k={np.median(odc_ks):.1f}, "
              f"median TIR={np.median(odc_tirs):.1f}%")

    results["cross_cohort"] = {
        "ns_median_k": float(np.median(list(ns_k.values()))),
        "ns_median_tir": float(np.median(list(ns_tir.values()))),
        "odc_median_k": float(np.median(odc_ks)) if odc_ks else None,
        "odc_median_tir": float(np.median(odc_tirs)) if odc_tirs else None,
    }

    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    run()
