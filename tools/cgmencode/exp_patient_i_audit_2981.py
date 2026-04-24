"""EXP-2981 - Patient `i` representativeness audit.

Patient `i` drives the Loop overshoot finding from EXP-2979
(361 of 363 events in BG ∈ [70,100) rising no-carb).  Audit how
representative `i` is of the Loop_AB_ON cohort:

  * Total events per patient in the rising 70-100 stratum.
  * Baseline metrics per Loop_AB_ON patient (TIR, hypo rate,
    mean BG, mean SMB dose, daily SMB count).
  * BG-residency distribution to test whether c/d/e/g
    "rarely descend into 70-100" (use-pattern) vs `i`
    "lives there often" (profile/aggressiveness).
  * Honest verdict: representative or outlier.

Scope: AID-author audience.
What this is NOT: a per-patient therapy recommendation;
not a TIR comparison across designs.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
SIMP = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = REPO / "externals" / "experiments" / "exp-2981_summary.json"

LOOP_AB_OFF = {"a", "f"}
LOOP_AB_ON = {"c", "d", "e", "g", "i"}

BAND_LO, BAND_HI = 70.0, 100.0
PRE_NO_CARB = 24
VEL_WIN = 6
RISING_VEL = 0.5


def baseline_metrics(sub):
    bg = sub["glucose"].dropna().values
    smb = sub["bolus_smb"].fillna(0).values
    n = len(bg)
    if n == 0:
        return {}
    bins = {
        "<54": float((bg < 54).mean()),
        "<70": float((bg < 70).mean()),
        "70_100": float(((bg >= 70) & (bg < 100)).mean()),
        "100_140": float(((bg >= 100) & (bg < 140)).mean()),
        "70_180": float(((bg >= 70) & (bg <= 180)).mean()),
        ">180": float((bg > 180).mean()),
        ">250": float((bg > 250).mean()),
    }
    smb_pos = smb[smb > 0]
    days = max(1.0, (sub["time"].max() - sub["time"].min()).total_seconds() / 86400.0)
    return {
        "n_5min_rows": int(n),
        "mean_bg": float(bg.mean()),
        "median_bg": float(np.median(bg)),
        "tir_70_180": bins["70_180"],
        "frac_in_70_100": bins["70_100"],
        "frac_below_70": bins["<70"],
        "frac_above_180": bins[">180"],
        "frac_above_250": bins[">250"],
        "smb_count": int((smb > 0).sum()),
        "smb_per_day": float((smb > 0).sum() / days),
        "smb_dose_median_U": float(np.median(smb_pos)) if len(smb_pos) else float("nan"),
        "smb_dose_mean_U": float(smb_pos.mean()) if len(smb_pos) else float("nan"),
    }


def main():
    simp = pd.read_parquet(SIMP, columns=["patient_id"]).drop_duplicates("patient_id")
    cols = ["patient_id", "time", "glucose", "carbs", "bolus_smb"]
    g = pd.read_parquet(GRID, columns=cols)
    g = g[g.patient_id.isin(LOOP_AB_ON)].dropna(subset=["glucose"]).sort_values(["patient_id", "time"]).reset_index(drop=True)

    base_rows = []
    rising_rows = []
    overshoot_rows = []
    for pid, sub in g.groupby("patient_id"):
        b = baseline_metrics(sub)
        b["patient_id"] = pid
        base_rows.append(b)

        sub = sub.sort_values("time").reset_index(drop=True)
        bg = sub["glucose"].values
        smb = sub["bolus_smb"].fillna(0).values
        carbs = sub["carbs"].fillna(0).values
        carbs_pre = sub["carbs"].fillna(0).shift(1).rolling(PRE_NO_CARB, min_periods=1).sum().fillna(0).values
        n = len(sub)

        n_smb_70_100 = 0
        n_smb_70_100_rising = 0
        n_smb_70_100_rising_nocarb = 0
        # Also compute time spent rising in 70-100 (denominator for "use rate")
        n_5min_70_100 = 0
        n_5min_70_100_rising = 0

        for i in range(VEL_WIN, n):
            if np.isnan(bg[i]):
                continue
            in_band = BAND_LO <= bg[i] < BAND_HI
            if in_band:
                n_5min_70_100 += 1
                ys_pre = bg[i - VEL_WIN:i + 1]
                if not np.any(np.isnan(ys_pre)):
                    xs = np.arange(VEL_WIN + 1) * 5.0
                    xm = xs.mean(); ym = ys_pre.mean()
                    denom = float(np.sum((xs - xm) ** 2))
                    vel = float(np.sum((xs - xm) * (ys_pre - ym)) / denom) if denom > 0 else 0.0
                    if vel > RISING_VEL:
                        n_5min_70_100_rising += 1
                if smb[i] > 0:
                    n_smb_70_100 += 1
                    ys_pre = bg[i - VEL_WIN:i + 1]
                    if not np.any(np.isnan(ys_pre)):
                        xs = np.arange(VEL_WIN + 1) * 5.0
                        xm = xs.mean(); ym = ys_pre.mean()
                        denom = float(np.sum((xs - xm) ** 2))
                        vel = float(np.sum((xs - xm) * (ys_pre - ym)) / denom) if denom > 0 else 0.0
                        if vel > RISING_VEL:
                            n_smb_70_100_rising += 1
                            if carbs_pre[i] == 0 and carbs[i] == 0:
                                n_smb_70_100_rising_nocarb += 1

        rising_rows.append({
            "patient_id": pid,
            "n_5min_in_70_100": n_5min_70_100,
            "n_5min_in_70_100_rising": n_5min_70_100_rising,
            "n_smb_in_70_100": n_smb_70_100,
            "n_smb_in_70_100_rising": n_smb_70_100_rising,
            "n_smb_in_70_100_rising_nocarb": n_smb_70_100_rising_nocarb,
        })

    base_df = pd.DataFrame(base_rows).set_index("patient_id").sort_index()
    rising_df = pd.DataFrame(rising_rows).set_index("patient_id").sort_index()
    merged = base_df.join(rising_df)
    print("=== Loop_AB_ON baseline + rising-stratum event counts ===")
    print(merged.to_string())

    # Outlier check on patient i
    print("\n=== Patient i vs cohort (median ± IQR of c/d/e/g) ===")
    others = merged.drop(index="i")
    i_row = merged.loc["i"]
    cmp_rows = []
    for col in merged.columns:
        try:
            o = others[col].dropna()
            if not len(o):
                continue
            med = float(o.median())
            q25, q75 = float(o.quantile(0.25)), float(o.quantile(0.75))
            iqr = q75 - q25
            iv = float(i_row[col])
            outlier = (iv < q25 - 1.5 * iqr) or (iv > q75 + 1.5 * iqr)
            cmp_rows.append({"metric": col, "i": iv, "others_median": med,
                             "others_iqr": iqr, "is_outlier": bool(outlier)})
        except Exception:
            continue
    cmp = pd.DataFrame(cmp_rows)
    print(cmp.to_string(index=False))

    out = {
        "scope": "Patient i representativeness within Loop_AB_ON",
        "filters": {"bg_band": [BAND_LO, BAND_HI], "rising_vel_min_mg_per_min": RISING_VEL,
                    "no_carb_min": PRE_NO_CARB * 5},
        "per_patient": merged.reset_index().to_dict(orient="records"),
        "i_vs_others": cmp.to_dict(orient="records"),
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2981] {OUT}")


if __name__ == "__main__":
    main()
