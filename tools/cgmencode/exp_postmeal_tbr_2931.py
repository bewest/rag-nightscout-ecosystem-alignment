"""EXP-2931 - Post-meal TBR by design: does oref1 front-loading carry hypo cost?

EXP-2925 confirmed oref1 Pareto-dominates Loop on day-level TBR.
But EXP-2930 showed oref1 delivers 2.2-6.6x more SMB dose in
0-60min post-meal than Loop autobolus. Hypothesis A: oref1's
front-loading creates more meal-window hypo (no free lunch).
Hypothesis B: oref1's UAM dose is appropriately calibrated to
the actual carb absorption, so peak BG is lower without hypo.

Method per patient:
  1. Same meal events as EXP-2930 (carbs > 5g, 240min isolation).
  2. For each meal, compute fraction of cells in 0-30, 30-60,
     60-120, 120-240 min post-meal where glucose < 70.
  3. Per-patient mean across meals, then design-level mean + boot CI.

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
OUT = REPO / "externals" / "experiments" / "exp-2931_summary.json"

RNG = np.random.default_rng(2931)
N_BOOT = 2000
TBR = 70
SEVERE = 54

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

    g = pd.read_parquet(GRID, columns=["patient_id", "time", "glucose", "carbs"])
    g = g[g.patient_id.isin(set(simp.patient_id))].sort_values(["patient_id", "time"]).reset_index(drop=True)
    g["carbs"] = g["carbs"].fillna(0.0)

    meal_records = []
    for pid, sub in g.groupby("patient_id"):
        sub = sub.reset_index(drop=True)
        is_meal = sub["carbs"] > 5.0
        meal_idx = np.where(is_meal.values)[0]
        if len(meal_idx) == 0:
            continue

        prev_carb_t = -10**9
        for i in meal_idx:
            t = sub["time"].iloc[i].value / 1e9 / 60
            if t - prev_carb_t < 240:
                prev_carb_t = t
                continue
            prev_carb_t = t

            window = sub.iloc[i:i+49]
            if len(window) < 24:
                continue
            ts = window["time"].values
            t0 = ts[0]
            mins = (ts - t0) / np.timedelta64(1, "m")
            glu = window["glucose"].values
            mask_valid = ~np.isnan(glu)

            def frac(lo, hi, threshold):
                m = (mins >= lo) & (mins < hi) & mask_valid
                if m.sum() == 0:
                    return float("nan")
                return float((glu[m] < threshold).mean()) * 100

            def peak(lo, hi):
                m = (mins >= lo) & (mins < hi) & mask_valid
                if m.sum() == 0:
                    return float("nan")
                return float(np.nanmax(glu[m]))

            def trough(lo, hi):
                m = (mins >= lo) & (mins < hi) & mask_valid
                if m.sum() == 0:
                    return float("nan")
                return float(np.nanmin(glu[m]))

            meal_records.append({
                "patient_id": pid,
                "tbr_0_30": frac(0, 30, TBR), "tbr_30_60": frac(30, 60, TBR),
                "tbr_60_120": frac(60, 120, TBR), "tbr_120_240": frac(120, 240, TBR),
                "tbr_severe_60_240": frac(60, 240, SEVERE),
                "peak_0_240": peak(0, 240),
                "trough_60_240": trough(60, 240),
            })

    meals = pd.DataFrame(meal_records)
    print(f"Meals: {len(meals)} across {meals.patient_id.nunique()} patients")

    per_pat = meals.groupby("patient_id").mean(numeric_only=True).reset_index().merge(simp, on="patient_id")

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
    print(per_pat[["patient_id", "design",
                   "tbr_0_30", "tbr_30_60", "tbr_60_120", "tbr_120_240",
                   "tbr_severe_60_240", "peak_0_240", "trough_60_240"]].round(2).to_string(index=False))

    metrics = ["tbr_0_30", "tbr_30_60", "tbr_60_120", "tbr_120_240",
               "tbr_severe_60_240", "peak_0_240", "trough_60_240"]
    print("\n=== Design-level (mean of per-patient mean) ===")
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
            print(f"    {m:25s} = {row[m]:7.2f}  CI[{row[f'{m}_ci_lo']:7.2f}, {row[f'{m}_ci_hi']:7.2f}]")

    # Pairwise gap oref1 - design
    print("\n=== Pairwise gap (oref1 - design, raw units) ===")
    pairs = []
    oref1_sub = per_pat[per_pat.design == "oref1"]
    for d in ["Loop_AB_OFF", "Loop_AB_ON"]:
        cmp = per_pat[per_pat.design == d]
        for m in metrics:
            ref = oref1_sub[m].dropna().values
            cmp_v = cmp[m].dropna().values
            if len(ref) < 1 or len(cmp_v) < 1:
                continue
            gap = float(ref.mean() - cmp_v.mean())
            if len(ref) >= 2 and len(cmp_v) >= 2:
                br = RNG.choice(ref, size=(N_BOOT, len(ref)), replace=True).mean(axis=1)
                bc = RNG.choice(cmp_v, size=(N_BOOT, len(cmp_v)), replace=True).mean(axis=1)
                ds = br - bc
                ci_lo, ci_hi = float(np.percentile(ds, 2.5)), float(np.percentile(ds, 97.5))
                sig = (ci_lo > 0) or (ci_hi < 0)
            else:
                ci_lo = ci_hi = float("nan"); sig = None
            pairs.append({"design": d, "metric": m, "gap_oref1_minus_design": gap,
                          "ci_lo": ci_lo, "ci_hi": ci_hi, "sig": sig})
            tag = "*" if sig else " "
            print(f"  {d:12s} {m:25s} = {gap:+7.2f}  CI[{ci_lo:+7.2f},{ci_hi:+7.2f}] {tag}")

    out = {
        "scope": "Post-meal TBR/peak/trough by design (no free lunch check)",
        "n_meals": int(len(meals)),
        "design_summary": rows,
        "pairs_oref1_minus_design": pairs,
        "per_patient": per_pat.to_dict(orient="records"),
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2931] {OUT}")


if __name__ == "__main__":
    main()
