"""EXP-2933 - Pre-meal context decomposition of early post-meal TBR.

EXP-2931 found oref1 has +2.55pp TBR in 0-30 min post-meal vs
Loop_AB_ON. Hypothesis: this is pre-meal context (oref1 patients
enter meals from tighter BG distribution), not post-bolus over-
dosing. Test: stratify by pre-meal BG tertile. If gap shrinks
to non-sig within tertiles, interpretation confirmed.

Method per patient:
  1. Same meal events as EXP-2930/2931.
  2. Capture pre_meal_bg = glucose at meal cell (i==0).
  3. Bin pre-meal BG into tertiles defined globally.
  4. Per (design, pre_meal_bin), compute mean per-patient TBR 0-30.
  5. Bootstrap CI on within-bin design gap.

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
OUT = REPO / "externals" / "experiments" / "exp-2933_summary.json"

RNG = np.random.default_rng(2933)
N_BOOT = 2000
TBR = 70

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
        prev_carb_t = -10**9
        for i in meal_idx:
            t = sub["time"].iloc[i].value / 1e9 / 60
            if t - prev_carb_t < 240:
                prev_carb_t = t
                continue
            prev_carb_t = t
            window = sub.iloc[i:i+7]  # 30 min
            if len(window) < 6:
                continue
            ts = window["time"].values
            mins = (ts - ts[0]) / np.timedelta64(1, "m")
            glu = window["glucose"].values
            pre_bg = float(glu[0]) if not np.isnan(glu[0]) else float("nan")
            mask = (mins >= 0) & (mins < 30) & ~np.isnan(glu)
            if mask.sum() == 0:
                continue
            tbr_0_30 = float((glu[mask] < TBR).mean()) * 100
            meal_records.append({
                "patient_id": pid,
                "pre_meal_bg": pre_bg,
                "tbr_0_30": tbr_0_30,
            })

    meals = pd.DataFrame(meal_records).dropna()
    print(f"Meals with pre-BG: {len(meals)} across {meals.patient_id.nunique()} patients")

    # Global pre-BG tertiles
    meals["pre_bin"] = pd.qcut(meals["pre_meal_bg"], 3, labels=["low_pre", "mid_pre", "high_pre"])
    print("\nPre-meal BG tertile cutpoints:")
    print(meals.groupby("pre_bin")["pre_meal_bg"].agg(["min", "max", "mean", "count"]).round(1))

    # Per (patient, pre_bin) mean TBR 0-30
    per = meals.groupby(["patient_id", "pre_bin"], observed=True).agg(
        n_meals=("tbr_0_30", "size"),
        tbr_0_30=("tbr_0_30", "mean"),
        pre_bg=("pre_meal_bg", "mean"),
    ).reset_index().merge(simp, on="patient_id")

    def design(row):
        if row["lineage"] == "oref1 (modern)":
            return "oref1"
        if row["patient_id"] in LOOP_AB_ON:
            return "Loop_AB_ON"
        if row["patient_id"] in LOOP_AB_OFF:
            return "Loop_AB_OFF"
        return None

    per["design"] = per.apply(design, axis=1)
    per = per.dropna(subset=["design"])

    # Pre-meal BG distribution by design (the confound itself)
    print("\n=== Pre-meal BG mean by design (the confound) ===")
    pre_by_design = meals.merge(simp, on="patient_id")
    pre_by_design["design"] = pre_by_design.apply(design, axis=1)
    print(pre_by_design.groupby("design")["pre_meal_bg"].agg(["mean", "median", "std", "count"]).round(1))

    # Distribution of meals across pre-BG tertiles by design
    print("\n=== Meal distribution across pre-BG tertiles (% of design's meals) ===")
    dist = (pre_by_design.groupby(["design", "pre_bin"], observed=True).size()
            / pre_by_design.groupby("design").size() * 100).unstack(fill_value=0).round(1)
    print(dist)

    # Within-bin TBR 0-30 gap oref1 - design
    print("\n=== Within-tertile TBR 0-30 gap (oref1 - design, pp) ===")
    pairs = []
    for binname in ["low_pre", "mid_pre", "high_pre"]:
        oref_v = per[(per.design == "oref1") & (per.pre_bin == binname)]["tbr_0_30"].values
        for d in ["Loop_AB_OFF", "Loop_AB_ON"]:
            cmp_v = per[(per.design == d) & (per.pre_bin == binname)]["tbr_0_30"].values
            if len(oref_v) == 0 or len(cmp_v) == 0:
                continue
            gap = float(oref_v.mean() - cmp_v.mean())
            if len(oref_v) >= 2 and len(cmp_v) >= 2:
                br = RNG.choice(oref_v, size=(N_BOOT, len(oref_v)), replace=True).mean(axis=1)
                bc = RNG.choice(cmp_v, size=(N_BOOT, len(cmp_v)), replace=True).mean(axis=1)
                ds = br - bc
                ci_lo, ci_hi = float(np.percentile(ds, 2.5)), float(np.percentile(ds, 97.5))
                sig = (ci_lo > 0) or (ci_hi < 0)
            else:
                ci_lo = ci_hi = float("nan"); sig = None
            pairs.append({"pre_bin": binname, "design": d,
                          "n_oref1": int(len(oref_v)), "n_design": int(len(cmp_v)),
                          "tbr_gap_oref1_minus_design": gap,
                          "ci_lo": ci_lo, "ci_hi": ci_hi, "sig": sig})
            tag = "*" if sig else " "
            print(f"  {binname:8s} vs {d:12s}: n={len(oref_v)},{len(cmp_v)} "
                  f"gap = {gap:+5.2f}pp  CI[{ci_lo:+.2f},{ci_hi:+.2f}] {tag}")

    out = {
        "scope": "Pre-meal context decomposition of early post-meal TBR",
        "n_meals": int(len(meals)),
        "pre_bg_distribution_by_design": pre_by_design.groupby("design")["pre_meal_bg"]
            .agg(["mean", "median", "std", "count"]).round(2).to_dict(),
        "meal_distribution_across_tertiles": dist.to_dict(),
        "within_tertile_pairs": pairs,
        "per_patient_bin": per.to_dict(orient="records"),
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2933] {OUT}")


if __name__ == "__main__":
    main()
