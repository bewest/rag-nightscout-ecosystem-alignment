"""EXP-2985 - Cross-patient overshoot rate at all BG bands (Loop_AB_ON).

EXP-2979's overshoot finding was one stratum (70-100 rising)
dominated by patient `i`.  Generalize: per Loop_AB_ON patient,
compute overshoot rate (% events crossing >180 within 60 min
of an SMB) by BG-band of SMB origin (no-carb).

Bands: <70, 70-100, 100-140, 140-180, 180-220, >220.

Test whether `i` is an overshoot outlier or representative
across bands.  If `i` is consistently high vs c/d/e/g, downgrade
EXP-2979's directional claim.

Scope: AID-author audience.
What this is NOT: a generalized clinical claim — Loop_AB_ON
n=5 patients only.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = REPO / "externals" / "experiments" / "exp-2985_summary.json"

LOOP_AB_ON = {"c", "d", "e", "g", "i"}
PRE_NO_CARB = 24
POST_WIN = 12   # 60 min
HYPO_BG = 70.0
OVERSHOOT_BG = 180.0

BANDS = [(0, 70), (70, 100), (100, 140), (140, 180), (180, 220), (220, 999)]


def band_label(bg):
    for lo, hi in BANDS:
        if lo <= bg < hi:
            return f"{lo}_{hi}"
    return None


def main():
    cols = ["patient_id", "time", "glucose", "carbs", "bolus_smb"]
    g = pd.read_parquet(GRID, columns=cols)
    g = g[g.patient_id.isin(LOOP_AB_ON)].dropna(subset=["glucose"])

    rows = []
    for pid, sub in g.groupby("patient_id"):
        sub = sub.sort_values("time").reset_index(drop=True)
        bg = sub["glucose"].values
        smb = sub["bolus_smb"].fillna(0).values
        carbs = sub["carbs"].fillna(0).values
        carbs_pre = sub["carbs"].fillna(0).shift(1).rolling(PRE_NO_CARB, min_periods=1).sum().fillna(0).values
        n = len(sub)
        for i in range(0, n - POST_WIN):
            if np.isnan(bg[i]) or smb[i] <= 0:
                continue
            if not (carbs_pre[i] == 0 and carbs[i] == 0):
                continue
            post60 = bg[i + 1:i + 1 + POST_WIN]
            if np.any(np.isnan(post60)):
                continue
            b = band_label(bg[i])
            if b is None:
                continue
            rows.append({
                "patient_id": pid, "band": b, "smb_dose_U": float(smb[i]),
                "overshoot_180": int(np.any(post60 > OVERSHOOT_BG)),
                "hypo_70": int(np.any(post60 < HYPO_BG)),
            })

    df = pd.DataFrame(rows)
    print(f"Total qualifying SMB events (no-carb, Loop_AB_ON): {len(df):,}")

    print("\n=== Per-patient × band overshoot/hypo rates ===")
    grp = df.groupby(["patient_id", "band"]).agg(
        n=("smb_dose_U", "size"),
        smb_med_U=("smb_dose_U", "median"),
        overshoot_rate=("overshoot_180", "mean"),
        hypo_rate=("hypo_70", "mean"),
    ).reset_index()
    print(grp.to_string(index=False))

    # i vs others per band
    print("\n=== `i` vs c/d/e/g median overshoot per band ===")
    cmp_rows = []
    for band, sub in grp.groupby("band"):
        i_row = sub[sub.patient_id == "i"]
        oth = sub[sub.patient_id != "i"]
        if not len(i_row) or not len(oth):
            continue
        i_os = float(i_row["overshoot_rate"].iloc[0])
        oth_med = float(oth["overshoot_rate"].median())
        oth_max = float(oth["overshoot_rate"].max())
        cmp_rows.append({"band": band, "i_overshoot": i_os,
                         "others_median": oth_med, "others_max": oth_max,
                         "i_n": int(i_row["n"].iloc[0]),
                         "others_n_total": int(oth["n"].sum()),
                         "i_higher_than_others_max": bool(i_os > oth_max)})
    cmp = pd.DataFrame(cmp_rows)
    print(cmp.to_string(index=False))

    # Pooled per-band (Loop_AB_ON cohort)
    pool = df.groupby("band").agg(
        n=("smb_dose_U", "size"),
        smb_med_U=("smb_dose_U", "median"),
        overshoot_rate=("overshoot_180", "mean"),
        hypo_rate=("hypo_70", "mean"),
    ).reset_index()
    print("\n=== Pooled Loop_AB_ON per band ===")
    print(pool.to_string(index=False))

    # Headline outlier verdict
    print("\n=== Verdict ===")
    if len(cmp):
        bands_i_outlier = cmp[cmp.i_higher_than_others_max].band.tolist()
        print(f"Bands where `i` overshoot > all of c/d/e/g: {bands_i_outlier}")
        n_cmp = len(cmp)
        n_out = len(bands_i_outlier)
        if n_out >= max(1, n_cmp // 2):
            print("→ `i` is an overshoot OUTLIER across most bands.")
        else:
            print("→ `i` is roughly representative of Loop_AB_ON overshoot.")

    out = {
        "scope": "Cross-patient overshoot per BG band (Loop_AB_ON)",
        "per_patient_band": grp.to_dict(orient="records"),
        "i_vs_others_per_band": cmp.to_dict(orient="records"),
        "pooled_per_band": pool.to_dict(orient="records"),
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2985] {OUT}")


if __name__ == "__main__":
    main()
