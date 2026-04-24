"""EXP-2958 - SMB-during-rising mechanism within-patient at sustained-high.

Refines synthesis lever (3): tests whether WITHIN-window SMB volume
(first 30 min after sustained-high detection) predicts subsequent
recovery within each patient's event history.

Window: bg crosses above 200, no carbs in prior 120 min.
Outcome: delta_60 = bg(+60min) - bg(entry).
Predictor: cumulative bolus_smb across cells [0, +30 min].
Per-patient regression: single-predictor AND multi-factor controlling
for bg_entry, scheduled_basal_rate, and prior 60 min bolus.
Sign test across patients. Report by design.

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
OUT = REPO / "externals" / "experiments" / "exp-2958_summary.json"

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


def main():
    simp = pd.read_parquet(SIMP, columns=["patient_id", "lineage"]).drop_duplicates("patient_id")
    pid_to_lin = dict(zip(simp.patient_id, simp.lineage))

    cols = ["patient_id", "time", "glucose", "carbs", "bolus", "bolus_smb",
            "actual_basal_rate", "scheduled_basal_rate"]
    g = pd.read_parquet(GRID, columns=cols)
    g = g[g.patient_id.isin(set(simp.patient_id))].dropna(subset=["glucose"])
    g = g.sort_values(["patient_id", "time"]).reset_index(drop=True)

    PRE_CARB = 24  # 120 min
    SMB_WIN = 6    # 30 min forward
    OUT_WIN = 12   # 60 min forward
    PRE_BOLUS = 12  # 60 min prior bolus

    rows = []
    for pid, sub in g.groupby("patient_id"):
        d = design_of(pid, pid_to_lin.get(pid, ""))
        if d is None:
            continue
        sub = sub.sort_values("time").reset_index(drop=True)
        bg = sub["glucose"].values
        bg_prev = sub["glucose"].shift(1).values
        bg_max_pre = sub["glucose"].shift(1).rolling(PRE_CARB, min_periods=1).max().values
        carbs_pre = sub["carbs"].fillna(0).shift(1).rolling(PRE_CARB, min_periods=1).sum().fillna(0).values
        bolus_pre = sub["bolus"].fillna(0).shift(1).rolling(PRE_BOLUS, min_periods=1).sum().fillna(0).values
        sched = sub["scheduled_basal_rate"].fillna(0).values
        smb = sub["bolus_smb"].fillna(0).values
        carbs = sub["carbs"].fillna(0).values
        n = len(sub)
        for i in range(PRE_CARB, n - OUT_WIN):
            if not (bg[i] >= 200 and bg_prev[i] < 200 and bg_max_pre[i] < 200
                    and carbs_pre[i] == 0
                    and carbs[i:i + OUT_WIN].sum() == 0):
                continue
            smb_30 = float(smb[i:i + SMB_WIN].sum())
            rows.append({
                "patient_id": pid, "design": d,
                "smb_30": smb_30,
                "bg_entry": float(bg[i]),
                "sched_basal": float(sched[i]),
                "bolus_pre60": float(bolus_pre[i]),
                "bg_60": float(bg[i + OUT_WIN]),
                "delta_60": float(bg[i + OUT_WIN] - bg[i]),
            })

    ev = pd.DataFrame(rows)
    print(f"Total sustained-high events: {len(ev):,}")
    if len(ev) == 0:
        print("No events; aborting.")
        return

    print("\n=== SMB-30 distribution by design ===")
    print(ev.groupby("design").agg(
        n=("smb_30", "size"),
        smb_mean=("smb_30", "mean"),
        smb_p90=("smb_30", lambda x: x.quantile(0.9)),
        smb_zero_pct=("smb_30", lambda x: (x == 0).mean()),
        delta_60_mean=("delta_60", "mean"),
    ).round(3).to_string())

    from scipy import stats
    from scipy.stats import binomtest
    per_pat = []
    for pid, sub in ev.groupby("patient_id"):
        if len(sub) < 20 or sub["smb_30"].std() < 1e-5:
            continue
        slope_s, _, r, p_s, _ = stats.linregress(sub["smb_30"], sub["delta_60"])
        try:
            X = np.column_stack([sub["smb_30"], sub["bg_entry"], sub["sched_basal"],
                                 sub["bolus_pre60"], np.ones(len(sub))])
            beta, *_ = np.linalg.lstsq(X, sub["delta_60"].values, rcond=None)
            slope_mf = float(beta[0])
        except Exception:
            slope_mf = np.nan
        per_pat.append({
            "patient_id": pid,
            "design": sub["design"].iloc[0],
            "n_events": len(sub),
            "smb_mean": float(sub["smb_30"].mean()),
            "slope_single": float(slope_s), "p_single": float(p_s),
            "slope_mf": slope_mf,
        })
    pp = pd.DataFrame(per_pat)
    print(f"\nPatients with >=20 events & SMB variability: {len(pp)}")
    if len(pp) == 0:
        print("No qualified patients (likely Loop has zero SMB). Reporting by design only.")
    else:
        print("\n=== Per-patient slopes ===")
        print(pp.sort_values("design").to_string(index=False))

        for label, col in [("single-predictor slope (delta_60 ~ smb_30)", "slope_single"),
                           ("multi-factor slope (smb_30 | bg_entry, sched_basal, bolus_pre60)", "slope_mf")]:
            valid = pp[col].dropna()
            if len(valid) == 0:
                continue
            n_neg = int((valid < 0).sum())
            bt = binomtest(n_neg, n=len(valid), p=0.5, alternative="greater")
            t, p_t = stats.ttest_1samp(valid, 0.0)
            print(f"\n=== {label} ===")
            print(f"  n_pat={len(valid)}, n_neg={n_neg}, sign-test p={bt.pvalue:.3g}")
            print(f"  median={valid.median():+.3f}, mean={valid.mean():+.3f}, t-test p={p_t:.3g}")

        print("\n=== By design (single-predictor) ===")
        for dlab, sub in pp.groupby("design"):
            n_neg_d = int((sub.slope_single < 0).sum())
            print(f"  {dlab:14s}: n={len(sub)}, median slope {sub.slope_single.median():+.3f}, "
                  f"{n_neg_d}/{len(sub)} negative")

    out = {
        "scope": "within-patient SMB-during-rising mechanism at sustained-high",
        "n_events": int(len(ev)),
        "n_patients_qualified": int(len(pp)),
        "by_design_events": ev.groupby("design").agg(
            n=("smb_30", "size"),
            smb_mean=("smb_30", "mean"),
            delta_60_mean=("delta_60", "mean"),
        ).reset_index().to_dict(orient="records"),
        "per_patient": pp.to_dict(orient="records") if len(pp) else [],
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2958] {OUT}")


if __name__ == "__main__":
    main()
