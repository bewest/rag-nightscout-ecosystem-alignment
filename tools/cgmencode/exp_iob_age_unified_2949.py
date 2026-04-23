"""EXP-2949 - IOB-age unified test via insulin_activity / iob ratio.

Cleaner operationalisation of the IOB-age framework (EXP-2944/2946/2947).
The grid has both `iob` (total insulin remaining) and `insulin_activity`
(integrated activity curve = current glucose-lowering rate). Their RATIO
is a direct measurement of IOB FRESHNESS:

  freshness = insulin_activity / iob

  - High freshness: IOB was just delivered, near peak action (HAZARDOUS
    during BG fall, BENEFICIAL during BG rise)
  - Low freshness: IOB is post-peak, decaying (BUFFER during BG fall,
    LATE-ACTING during BG rise)

The unified hypothesis predicts:

  At HYPO descent entry (BG=80 falling): oref1 < Loop_AB_ON
    (oref1's IOB is staler at the hazard window)

  At sustained-high entry (BG≥180 climb): oref1 > Loop_AB_ON
    (oref1 has placed dose earlier; activity is peaking when needed)

  At meal-onset (carb event): oref1 > Loop_AB_ON
    (UAM/pre-fire makes activity available during absorption)

Also measures `time_since_bolus_min` at each anchor as a coarser
secondary variable.

Scope: AID-author audience.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
SIMP = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = REPO / "externals" / "experiments" / "exp-2949_summary.json"

LOOP_AB_OFF = {"a", "f"}
LOOP_AB_ON = {"c", "d", "e", "g", "i"}
OREF0_PATS = {"odc-74077367", "odc-86025410", "odc-96254963"}


def design_of(pid, lin):
    if pid in OREF0_PATS:
        return "oref0"
    if lin == "oref1 (modern)":
        return "oref1"
    if pid in LOOP_AB_ON:
        return "Loop_AB_ON"
    if pid in LOOP_AB_OFF:
        return "Loop_AB_OFF"
    return None


def freshness(activity, iob):
    if iob is None or iob <= 1e-3:
        return np.nan
    return float(activity / iob)


def main():
    simp = pd.read_parquet(SIMP, columns=["patient_id", "lineage"]).drop_duplicates("patient_id")
    pid_to_lin = dict(zip(simp.patient_id, simp.lineage))

    cols = ["patient_id", "time", "glucose", "carbs", "iob",
            "insulin_activity", "time_since_bolus_min"]
    g = pd.read_parquet(GRID, columns=cols)
    g = g[g.patient_id.isin(set(simp.patient_id))].dropna(subset=["glucose", "iob"])
    g = g.sort_values(["patient_id", "time"]).reset_index(drop=True)

    hypo_rows, high_rows, meal_rows = [], [], []

    for pid, sub in g.groupby("patient_id"):
        d = design_of(pid, pid_to_lin.get(pid, ""))
        if d is None:
            continue
        sub = sub.sort_values("time").reset_index(drop=True)
        bg = sub["glucose"].values
        bg_prev = sub["glucose"].shift(1).values
        bg_min_30 = sub["glucose"].shift(1).rolling(6, min_periods=1).min().values
        bg_max_30 = sub["glucose"].shift(1).rolling(6, min_periods=1).max().values
        carbs_60_pre = sub["carbs"].shift(1).rolling(12, min_periods=1).sum().fillna(0).values
        iob = sub["iob"].values
        act = sub["insulin_activity"].fillna(0).values
        tsb = sub["time_since_bolus_min"].values
        carbs = sub["carbs"].fillna(0).values

        # HYPO ENTRY: BG crosses 80 falling, all >80 in prior 30min, no carbs ±60
        for i in range(12, len(sub) - 12):
            if not (bg[i] <= 80 and bg_prev[i] > 80 and bg_min_30[i] > 80
                    and carbs_60_pre[i] == 0):
                continue
            if sub.iloc[i:i+12]["carbs"].fillna(0).sum() > 0:
                continue
            hypo_rows.append({
                "patient_id": pid, "design": d,
                "freshness": freshness(act[i], iob[i]),
                "iob": float(iob[i]), "activity": float(act[i]),
                "time_since_bolus": float(tsb[i]) if not np.isnan(tsb[i]) else np.nan,
            })

        # SUSTAINED-HIGH ENTRY: BG crosses 180 climbing, all <180 in prior 30min,
        # no carbs in 60min after (correction-only), no carbs in 30min before
        for i in range(6, len(sub) - 12):
            if not (bg[i] >= 180 and bg_prev[i] < 180 and bg_max_30[i] < 180
                    and sub.iloc[i-6:i]["carbs"].fillna(0).sum() == 0
                    and sub.iloc[i:i+12]["carbs"].fillna(0).sum() == 0):
                continue
            high_rows.append({
                "patient_id": pid, "design": d,
                "freshness": freshness(act[i], iob[i]),
                "iob": float(iob[i]), "activity": float(act[i]),
                "time_since_bolus": float(tsb[i]) if not np.isnan(tsb[i]) else np.nan,
            })

        # MEAL ONSET: carbs > 20g, prior 6h no carbs, BG in 80-180 quiet pre
        carbs_pre6h = sub["carbs"].shift(1).rolling(72, min_periods=1).sum().fillna(0).values
        for i in range(72, len(sub) - 12):
            if not (carbs[i] > 20 and carbs_pre6h[i] == 0
                    and 80 <= bg[i] <= 180):
                continue
            meal_rows.append({
                "patient_id": pid, "design": d,
                "freshness": freshness(act[i], iob[i]),
                "iob": float(iob[i]), "activity": float(act[i]),
                "time_since_bolus": float(tsb[i]) if not np.isnan(tsb[i]) else np.nan,
            })

    hypo = pd.DataFrame(hypo_rows)
    high = pd.DataFrame(high_rows)
    meal = pd.DataFrame(meal_rows)

    print(f"Events: hypo={len(hypo):,} sustained-high={len(high):,} meal={len(meal):,}\n")

    out = {"scope": "IOB-age unified test via insulin_activity/iob ratio"}

    for label, df in [("HYPO_ENTRY (BG=80 falling)", hypo),
                      ("SUSTAINED_HIGH_ENTRY (BG=180 climbing)", high),
                      ("MEAL_ONSET (>20g carbs, quiet pre)", meal)]:
        if len(df) == 0:
            continue
        print(f"=== {label} ===")
        s = df.groupby("design").agg(
            n=("freshness", "size"),
            freshness=("freshness", "mean"),
            iob=("iob", "mean"),
            activity=("activity", "mean"),
            tsb_min=("time_since_bolus", "median"),
        ).round(4)
        print(s.to_string())
        print()
        out[label] = s.reset_index().to_dict(orient="records")

        # Pairwise contrasts
        for a, b in [("Loop_AB_ON", "oref1"),
                     ("Loop_AB_OFF", "oref1"),
                     ("oref0", "oref1")]:
            xa = df[df.design == a]["freshness"].dropna().values
            xb = df[df.design == b]["freshness"].dropna().values
            if len(xa) > 5 and len(xb) > 5:
                from scipy import stats
                u, p = stats.mannwhitneyu(xa, xb, alternative="two-sided")
                print(f"    {a} vs {b}: Δfreshness {xa.mean()-xb.mean():+.4f} "
                      f"(MW p={p:.3g})")
        print()

    # UNIFIED test: at hypo, oref1<Loop; at high, oref1>Loop; opposite
    if len(hypo) and len(high):
        ho = hypo[hypo.design == "oref1"]["freshness"].mean()
        hL = hypo[hypo.design == "Loop_AB_ON"]["freshness"].mean()
        ko = high[high.design == "oref1"]["freshness"].mean()
        kL = high[high.design == "Loop_AB_ON"]["freshness"].mean()
        sign_hypo = "OREF1<LOOP (predicted)" if ho < hL else "OREF1>=LOOP (refuted)"
        sign_high = "OREF1>LOOP (predicted)" if ko > kL else "OREF1<=LOOP (refuted)"
        print(f"UNIFIED HYPOTHESIS:")
        print(f"  hypo freshness: {sign_hypo} (oref1 {ho:.4f}, Loop_AB_ON {hL:.4f})")
        print(f"  high freshness: {sign_high} (oref1 {ko:.4f}, Loop_AB_ON {kL:.4f})")
        out["unified"] = {
            "hypo_oref1": ho, "hypo_Loop_AB_ON": hL,
            "high_oref1": ko, "high_Loop_AB_ON": kL,
            "hypo_predicted": bool(ho < hL),
            "high_predicted": bool(ko > kL),
        }

    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2949] {OUT}")


if __name__ == "__main__":
    main()
