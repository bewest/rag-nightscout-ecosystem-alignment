"""EXP-2962 - Per-patient velocity-coupling at PP, oref1 vs Loop_AB_ON.

Tests whether the +1.36 oref1 slope (EXP-2960) is driven by 1-2 patients
or is consistent across the cohort. Within each patient with >= 30 PP
meal events, fit individual velocity-coupling slope. Report distribution,
sign-test, Mann-Whitney oref1 vs Loop_AB_ON.

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
OUT = REPO / "externals" / "experiments" / "exp-2962_summary.json"

LOOP_AB_OFF = {"a", "f"}
LOOP_AB_ON = {"c", "d", "e", "g", "i"}
OREF0_PATS = {"odc-74077367", "odc-86025410", "odc-96254963"}

MIN_EVENTS = 30


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
    g["bolus_total"] = g["bolus"].fillna(0) + g["bolus_smb"].fillna(0)
    g["basal_excess"] = ((g["actual_basal_rate"].fillna(0) -
                          g["scheduled_basal_rate"].fillna(0)) * 5.0 / 60.0).clip(lower=0)
    g["insulin_event"] = g["bolus_total"] + g["basal_excess"]

    PRE_CARB = 12
    VEL_WIN = 6
    INS_WIN = 12

    rows = []
    for pid, sub in g.groupby("patient_id"):
        d = design_of(pid, pid_to_lin.get(pid, ""))
        if d is None:
            continue
        sub = sub.sort_values("time").reset_index(drop=True)
        carbs = sub["carbs"].fillna(0).values
        carbs_pre = sub["carbs"].fillna(0).shift(1).rolling(PRE_CARB, min_periods=1).sum().fillna(0).values
        bg = sub["glucose"].values
        ins_evt = sub["insulin_event"].values
        n = len(sub)
        for i in range(0, n - INS_WIN):
            if not (carbs[i] >= 30 and carbs_pre[i] == 0):
                continue
            j = i + VEL_WIN
            xs = np.arange(VEL_WIN + 1) * 5.0
            ys = bg[i:j + 1]
            if np.any(np.isnan(ys)):
                continue
            xm = xs.mean(); ym = ys.mean()
            denom = float(np.sum((xs - xm) ** 2))
            if denom <= 0:
                continue
            vel = float(np.sum((xs - xm) * (ys - ym)) / denom)
            ins_60 = float(ins_evt[i:i + INS_WIN].sum())
            rows.append({
                "patient_id": pid, "design": d,
                "carbs_g": float(carbs[i]),
                "bg_entry": float(bg[i]),
                "vel_30": vel,
                "ins_60_total": ins_60,
            })

    ev = pd.DataFrame(rows)
    print(f"Total meal events: {len(ev):,}")

    from scipy import stats
    per_pat_rows = []
    for (pid, d), sub in ev.groupby(["patient_id", "design"]):
        if len(sub) < MIN_EVENTS:
            continue
        slope, _, _, p, se = stats.linregress(sub["vel_30"], sub["ins_60_total"])
        per_pat_rows.append({
            "patient_id": pid, "design": d, "n": int(len(sub)),
            "slope": float(slope), "se": float(se), "p": float(p),
        })
    pp = pd.DataFrame(per_pat_rows)
    print(f"\nPatients with >= {MIN_EVENTS} events: {len(pp)}")
    print(pp.sort_values(["design", "slope"]).to_string(index=False))

    print("\n=== Per-design slope distribution ===")
    summary = []
    for d, sub in pp.groupby("design"):
        slopes = sub["slope"].values
        n_pos = int((slopes > 0).sum())
        n_neg = int((slopes < 0).sum())
        # sign test: P(X >= n_pos | binomial(n, 0.5))
        from scipy.stats import binomtest
        bt = binomtest(n_pos, len(slopes), p=0.5, alternative="two-sided")
        print(f"\n  {d} (n_pat={len(slopes)})")
        print(f"    median slope = {float(np.median(slopes)):+.4f}")
        print(f"    mean   slope = {float(np.mean(slopes)):+.4f}  ({n_pos}+ / {n_neg}-)")
        print(f"    sign-test p = {bt.pvalue:.4g}")
        summary.append({
            "design": d, "n_pat": len(slopes),
            "median_slope": float(np.median(slopes)),
            "mean_slope": float(np.mean(slopes)),
            "min_slope": float(np.min(slopes)),
            "max_slope": float(np.max(slopes)),
            "n_positive": n_pos, "n_negative": n_neg,
            "sign_test_p": float(bt.pvalue),
        })

    # MWU oref1 vs Loop_AB_ON
    o1 = pp[pp["design"] == "oref1"]["slope"].values
    lon = pp[pp["design"] == "Loop_AB_ON"]["slope"].values
    if len(o1) >= 3 and len(lon) >= 3:
        mwu = stats.mannwhitneyu(o1, lon, alternative="greater")
        print(f"\n=== Mann-Whitney oref1 > Loop_AB_ON per-patient slopes ===")
        print(f"  U={mwu.statistic:.1f}  p(one-sided)={mwu.pvalue:.4g}")
        print(f"  oref1 slopes: {sorted(o1.round(3).tolist())}")
        print(f"  Loop_AB_ON  : {sorted(lon.round(3).tolist())}")
        mwu_p = float(mwu.pvalue)
        mwu_u = float(mwu.statistic)
    else:
        mwu_p = mwu_u = None

    # Robustness: leave-one-out for oref1 pooled slope
    oref1_pids = sorted(ev[ev["design"] == "oref1"]["patient_id"].unique())
    print("\n=== oref1 leave-one-patient-out pooled slopes ===")
    loo = []
    for pid in oref1_pids:
        sub = ev[(ev["design"] == "oref1") & (ev["patient_id"] != pid)]
        if len(sub) < 30:
            continue
        slope, _, _, p, se = stats.linregress(sub["vel_30"], sub["ins_60_total"])
        loo.append({"left_out": pid, "n": int(len(sub)), "slope": float(slope), "se": float(se)})
        print(f"    -{pid}: slope = {slope:+.4f} (n={len(sub)})")

    out = {
        "scope": "Per-patient velocity-coupling at PP",
        "min_events_per_patient": MIN_EVENTS,
        "n_patients_qualified": int(len(pp)),
        "per_patient_slopes": pp.to_dict(orient="records"),
        "per_design_summary": summary,
        "mwu_oref1_gt_loop_ab_on": {"U": mwu_u, "p_one_sided": mwu_p},
        "oref1_loo": loo,
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2962] {OUT}")


if __name__ == "__main__":
    main()
