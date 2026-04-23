"""EXP-2930 - SMB temporal alignment to meal events: Loop autobolus vs oref1.

EXP-2894 found cadence/size indistinguishable. EXP-2929 found
20.57pp PP TIR gap survives even when Loop has autobolus enabled.
Hypothesis: temporal alignment differs - oref1 UAM detection fires
SMBs earlier in absorption than Loop autobolus, and continues
delivering SMB-as-correction throughout absorption.

Method per patient:
  1. Identify meal events: carbs > 0 with no carbs in prior 240 min.
  2. For each meal, measure:
       - first_smb_latency_min: t(first SMB) - t(meal), capped at 240
       - smb_dose_0_30, 30_60, 60_120, 120_240 (units in time bins)
       - n_smb_0_30, 30_60, 60_120, 120_240 (count of SMB events)
  3. Aggregate per patient (median across meals), then per design.

Scope: design-feature characterisation. AID-author audience.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
SIMP = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = REPO / "externals" / "experiments" / "exp-2930_summary.json"

RNG = np.random.default_rng(2930)
N_BOOT = 2000

LOOP_AB_OFF = {"a", "f"}
LOOP_AB_ON = {"c", "d", "e", "g", "i"}


def boot_mean_ci(values: np.ndarray) -> tuple[float, float]:
    if len(values) < 2:
        v = float(values[0]) if len(values) == 1 else float("nan")
        return v, v
    samples = RNG.choice(values, size=(N_BOOT, len(values)), replace=True).mean(axis=1)
    return float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5))


def main() -> None:
    simp = pd.read_parquet(SIMP, columns=["patient_id", "lineage"]).drop_duplicates("patient_id")
    simp = simp[simp.lineage.isin(["Loop (iOS)", "oref1 (modern)"])]

    g = pd.read_parquet(GRID, columns=["patient_id", "time", "carbs", "bolus_smb"])
    g = g[g.patient_id.isin(set(simp.patient_id))].sort_values(["patient_id", "time"]).reset_index(drop=True)
    g["carbs"] = g["carbs"].fillna(0.0)
    g["bolus_smb"] = g["bolus_smb"].fillna(0.0)

    meal_records = []
    for pid, sub in g.groupby("patient_id"):
        sub = sub.reset_index(drop=True)
        # Meals: carbs > 5g and no carbs in last 240 min
        is_meal = sub["carbs"] > 5.0
        meal_idx = np.where(is_meal.values)[0]
        if len(meal_idx) == 0:
            continue

        prev_carb_t = -10**9
        for i in meal_idx:
            t = sub["time"].iloc[i].value / 1e9 / 60  # minutes since epoch
            if t - prev_carb_t < 240:
                prev_carb_t = t
                continue
            prev_carb_t = t

            window = sub.iloc[i:i+49]  # next ~240 min (5-min cells)
            if len(window) < 24:
                continue
            ts = window["time"].values
            t0 = ts[0]
            mins = (ts - t0) / np.timedelta64(1, "m")
            smb = window["bolus_smb"].values

            # First SMB latency
            first = np.where(smb > 0)[0]
            first_lat = float(mins[first[0]]) if len(first) > 0 else float("nan")

            def bin_sum(lo, hi):
                m = (mins >= lo) & (mins < hi)
                return float(smb[m].sum()), int((smb[m] > 0).sum())

            d0, n0 = bin_sum(0, 30)
            d1, n1 = bin_sum(30, 60)
            d2, n2 = bin_sum(60, 120)
            d3, n3 = bin_sum(120, 240)

            meal_records.append({
                "patient_id": pid,
                "first_smb_latency_min": first_lat,
                "smb_dose_0_30": d0, "smb_dose_30_60": d1,
                "smb_dose_60_120": d2, "smb_dose_120_240": d3,
                "n_smb_0_30": n0, "n_smb_30_60": n1,
                "n_smb_60_120": n2, "n_smb_120_240": n3,
            })

    meals = pd.DataFrame(meal_records)
    if meals.empty:
        print("no meals found")
        return

    print(f"Meals total: {len(meals)} across {meals.patient_id.nunique()} patients")

    # Per-patient medians
    per_pat = meals.groupby("patient_id").agg(
        n_meals=("first_smb_latency_min", "size"),
        first_smb_latency_med=("first_smb_latency_min", "median"),
        smb_dose_0_30_med=("smb_dose_0_30", "median"),
        smb_dose_30_60_med=("smb_dose_30_60", "median"),
        smb_dose_60_120_med=("smb_dose_60_120", "median"),
        smb_dose_120_240_med=("smb_dose_120_240", "median"),
        n_smb_0_30_mean=("n_smb_0_30", "mean"),
        n_smb_30_60_mean=("n_smb_30_60", "mean"),
        n_smb_60_120_mean=("n_smb_60_120", "mean"),
        n_smb_120_240_mean=("n_smb_120_240", "mean"),
    ).reset_index().merge(simp, on="patient_id")

    def design(row):
        if row["lineage"] == "oref1 (modern)":
            return "oref1"
        if row["patient_id"] in LOOP_AB_ON:
            return "Loop_AB_ON"
        if row["patient_id"] in LOOP_AB_OFF:
            return "Loop_AB_OFF"
        return None

    per_pat["design"] = per_pat.apply(design, axis=1)
    per_pat = per_pat.dropna(subset=["design"])

    print("\n=== Per-patient summary ===")
    print(per_pat[["patient_id", "design", "n_meals",
                   "first_smb_latency_med",
                   "smb_dose_0_30_med", "smb_dose_30_60_med",
                   "smb_dose_60_120_med", "smb_dose_120_240_med"]].to_string(index=False))

    print("\n=== Design-level (mean of per-patient median) ===")
    metrics = ["first_smb_latency_med",
               "smb_dose_0_30_med", "smb_dose_30_60_med",
               "smb_dose_60_120_med", "smb_dose_120_240_med",
               "n_smb_0_30_mean", "n_smb_30_60_mean",
               "n_smb_60_120_mean", "n_smb_120_240_mean"]
    rows = []
    for d, sub in per_pat.groupby("design"):
        row = {"design": d, "n_patients": int(len(sub))}
        for m in metrics:
            v = sub[m].dropna().values
            mean = float(v.mean()) if len(v) else float("nan")
            lo, hi = boot_mean_ci(v) if len(v) else (float("nan"), float("nan"))
            row[m] = mean
            row[f"{m}_ci_lo"] = lo
            row[f"{m}_ci_hi"] = hi
        rows.append(row)
        print(f"\n  {d} (n={len(sub)})")
        for m in metrics:
            print(f"    {m:30s} = {row[m]:7.2f}  CI[{row[f'{m}_ci_lo']:7.2f}, {row[f'{m}_ci_hi']:7.2f}]")

    out = {
        "scope": "SMB temporal alignment to meal events",
        "n_meals_total": int(len(meals)),
        "design_summary": rows,
        "per_patient": per_pat.to_dict(orient="records"),
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2930] {OUT}")


if __name__ == "__main__":
    main()
