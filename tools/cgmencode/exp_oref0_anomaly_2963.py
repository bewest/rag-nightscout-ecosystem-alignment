"""EXP-2963 - oref0 anomalous slope (-0.27) investigation at PP.

EXP-2960 found oref0 had a NEGATIVE velocity-vs-insulin slope at PP.
This script:
(a) per-patient breakdown of the 3 oref0 patients
(b) report n_events per oref0 patient at PP
(c) bootstrap CI of pooled oref0 slope to test against null

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
OUT = REPO / "externals" / "experiments" / "exp-2963_summary.json"

OREF0_PATS = {"odc-74077367", "odc-86025410", "odc-96254963"}


def main():
    cols = ["patient_id", "time", "glucose", "carbs", "bolus", "bolus_smb",
            "actual_basal_rate", "scheduled_basal_rate"]
    g = pd.read_parquet(GRID, columns=cols)
    g = g[g.patient_id.isin(OREF0_PATS)].dropna(subset=["glucose"])
    g = g.sort_values(["patient_id", "time"]).reset_index(drop=True)
    g["bolus_total"] = g["bolus"].fillna(0) + g["bolus_smb"].fillna(0)
    g["basal_excess"] = ((g["actual_basal_rate"].fillna(0) -
                          g["scheduled_basal_rate"].fillna(0)) * 5.0 / 60.0).clip(lower=0)
    g["insulin_event"] = g["bolus_total"] + g["basal_excess"]

    PRE_CARB = 12
    VEL_WIN = 6
    INS_WIN = 12

    rows = []
    for pid, sub in g.groupby("patient_id"):
        sub = sub.sort_values("time").reset_index(drop=True)
        carbs = sub["carbs"].fillna(0).values
        carbs_pre = sub["carbs"].fillna(0).shift(1).rolling(PRE_CARB, min_periods=1).sum().fillna(0).values
        bg = sub["glucose"].values
        ins_evt = sub["insulin_event"].values
        bolus = sub["bolus"].fillna(0).values
        smb = sub["bolus_smb"].fillna(0).values
        basal_x = sub["basal_excess"].values
        n = len(sub)
        for i in range(0, n - INS_WIN):
            if not (carbs[i] >= 30 and carbs_pre[i] == 0):
                continue
            j = i + VEL_WIN
            xs = np.arange(VEL_WIN + 1) * 5.0
            ys = bg[i:j + 1]
            if np.any(np.isnan(ys)):
                continue
            xm = xs.mean()
            denom = float(np.sum((xs - xm) ** 2))
            if denom <= 0:
                continue
            ym = ys.mean()
            vel = float(np.sum((xs - xm) * (ys - ym)) / denom)
            rows.append({
                "patient_id": pid,
                "carbs_g": float(carbs[i]),
                "bg_entry": float(bg[i]),
                "vel_30": vel,
                "ins_60_total": float(ins_evt[i:i + INS_WIN].sum()),
                "ins_60_bolus": float(bolus[i:i + INS_WIN].sum()),
                "ins_60_smb": float(smb[i:i + INS_WIN].sum()),
                "ins_60_basal_excess": float(basal_x[i:i + INS_WIN].sum()),
            })

    ev = pd.DataFrame(rows)
    print(f"Total oref0 PP events: {len(ev):,}")

    from scipy import stats
    print("\n=== Per-patient (oref0) ===")
    per_pat = []
    for pid, sub in ev.groupby("patient_id"):
        if len(sub) < 5:
            print(f"  {pid}: n={len(sub)} TOO SMALL")
            per_pat.append({"patient_id": pid, "n": int(len(sub)), "slope": None})
            continue
        slope, intercept, r, p, se = stats.linregress(sub["vel_30"], sub["ins_60_total"])
        ci_lo = slope - 1.96 * se
        ci_hi = slope + 1.96 * se
        slope_smb, _, _, p_smb, _ = stats.linregress(sub["vel_30"], sub["ins_60_smb"])
        slope_bx, _, _, p_bx, _ = stats.linregress(sub["vel_30"], sub["ins_60_basal_excess"])
        slope_b, _, _, p_b, _ = stats.linregress(sub["vel_30"], sub["ins_60_bolus"])
        print(f"  {pid}: n={len(sub)}  vel_mean={sub['vel_30'].mean():+.3f}  "
              f"ins_total_mean={sub['ins_60_total'].mean():.2f}")
        print(f"     total slope = {slope:+.4f}  95%CI [{ci_lo:+.4f},{ci_hi:+.4f}]  p={p:.3g}")
        print(f"     bolus slope = {slope_b:+.4f} p={p_b:.3g}    "
              f"smb slope = {slope_smb:+.4f} p={p_smb:.3g}    "
              f"basal_x slope = {slope_bx:+.4f} p={p_bx:.3g}")
        per_pat.append({
            "patient_id": pid, "n": int(len(sub)),
            "vel_mean": float(sub["vel_30"].mean()),
            "ins_total_mean": float(sub["ins_60_total"].mean()),
            "slope_total": float(slope), "se": float(se),
            "ci_lo": float(ci_lo), "ci_hi": float(ci_hi), "p": float(p),
            "slope_bolus": float(slope_b),
            "slope_smb": float(slope_smb),
            "slope_basal_excess": float(slope_bx),
        })

    # Bootstrap CI for pooled oref0 slope
    print("\n=== Bootstrap pooled oref0 slope (B=2000) ===")
    rng = np.random.default_rng(2963)
    boot_slopes = []
    arr = ev[["vel_30", "ins_60_total"]].values
    for _ in range(2000):
        idx = rng.integers(0, len(arr), len(arr))
        s = arr[idx]
        sl, _, _, _, _ = stats.linregress(s[:, 0], s[:, 1])
        boot_slopes.append(sl)
    boot_slopes = np.array(boot_slopes)
    bci = (float(np.percentile(boot_slopes, 2.5)),
           float(np.percentile(boot_slopes, 97.5)))
    pooled_slope = float(np.mean(boot_slopes))
    print(f"  pooled bootstrap mean = {pooled_slope:+.4f}  "
          f"95%CI [{bci[0]:+.4f},{bci[1]:+.4f}]")

    # Leave-one-patient-out pooled slope
    print("\n=== Leave-one-patient-out pooled slopes ===")
    loo = []
    for pid in sorted(OREF0_PATS):
        sub = ev[ev["patient_id"] != pid]
        if len(sub) < 5:
            continue
        sl, _, _, p, se = stats.linregress(sub["vel_30"], sub["ins_60_total"])
        print(f"  -{pid}: slope={sl:+.4f}  n={len(sub)}  p={p:.3g}")
        loo.append({"left_out": pid, "n": int(len(sub)),
                    "slope": float(sl), "se": float(se)})

    out = {
        "scope": "oref0 anomalous slope investigation at PP",
        "n_events_total": int(len(ev)),
        "per_patient": per_pat,
        "bootstrap_pooled_slope_mean": pooled_slope,
        "bootstrap_pooled_slope_ci95": bci,
        "leave_one_out": loo,
        "code_note": (
            "Per externals/AndroidAPS/, the cohort's oref0 patients used "
            "AAPS releases predating SMB/UAM features, so the controller's "
            "only response channel at PP is temp-basal modulation."
        ),
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2963] {OUT}")


if __name__ == "__main__":
    main()
