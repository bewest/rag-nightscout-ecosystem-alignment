"""EXP-2971 - Per-patient SMB-channel velocity-coupling at the 70-100 no-carb sweet spot.

EXP-2966 found Loop_AB_ON SMB slope 1.5x oref1 at 70-100 mg/dL in
the no-carb context, with disjoint pooled 95% CIs at N>>100k. This
script tests whether that pooled difference survives a per-patient
sign-test and a between-design MWU.

Scope: AID-author audience.
What this is NOT: per-patient therapy advice.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
SIMP = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = REPO / "externals" / "experiments" / "exp-2971_summary.json"

LOOP_AB_OFF = {"a", "f"}
LOOP_AB_ON = {"c", "d", "e", "g", "i"}
OREF0_PATS = {"odc-74077367", "odc-86025410", "odc-96254963"}

MIN_EVENTS = 30
BAND_LO, BAND_HI = 70.0, 100.0


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
    g["basal_excess"] = ((g["actual_basal_rate"].fillna(0) -
                          g["scheduled_basal_rate"].fillna(0)) * 5.0 / 60.0).clip(lower=0)

    PRE_NO_CARB = 24  # 120 min
    VEL_WIN = 6
    INS_WIN = 12

    rows = []
    for pid, sub in g.groupby("patient_id"):
        d = design_of(pid, pid_to_lin.get(pid, ""))
        if d is None:
            continue
        sub = sub.sort_values("time").reset_index(drop=True)
        carbs = sub["carbs"].fillna(0).values
        carbs_pre = sub["carbs"].fillna(0).shift(1).rolling(PRE_NO_CARB, min_periods=1).sum().fillna(0).values
        bg = sub["glucose"].values
        smb = sub["bolus_smb"].fillna(0).values
        basal_x = sub["basal_excess"].values
        bolus = sub["bolus"].fillna(0).values
        n = len(sub)
        for i in range(0, n - INS_WIN):
            if np.isnan(bg[i]):
                continue
            if not (BAND_LO <= bg[i] < BAND_HI):
                continue
            if not (carbs_pre[i] == 0 and carbs[i] == 0):
                continue
            j = i + VEL_WIN
            ys = bg[i:j + 1]
            if np.any(np.isnan(ys)):
                continue
            xs = np.arange(VEL_WIN + 1) * 5.0
            xm = xs.mean(); ym = ys.mean()
            denom = float(np.sum((xs - xm) ** 2))
            if denom <= 0:
                continue
            vel = float(np.sum((xs - xm) * (ys - ym)) / denom)
            rows.append({
                "patient_id": pid, "design": d, "vel_30": vel,
                "ins_60_smb": float(smb[i:i + INS_WIN].sum()),
                "ins_60_basal_excess": float(basal_x[i:i + INS_WIN].sum()),
                "ins_60_bolus": float(bolus[i:i + INS_WIN].sum()),
            })

    ev = pd.DataFrame(rows)
    print(f"Total no-carb 70-100 windows: {len(ev):,}")

    from scipy import stats
    from scipy.stats import binomtest

    pp_rows = []
    for (pid, d), sub in ev.groupby(["patient_id", "design"]):
        if len(sub) < MIN_EVENTS:
            continue
        out = {"patient_id": pid, "design": d, "n": int(len(sub))}
        for label, col in [("smb", "ins_60_smb"),
                           ("basal_x", "ins_60_basal_excess"),
                           ("bolus", "ins_60_bolus")]:
            sl, _, _, p, se = stats.linregress(sub["vel_30"], sub[col])
            out[f"slope_{label}"] = float(sl)
            out[f"p_{label}"] = float(p)
        pp_rows.append(out)
    pp = pd.DataFrame(pp_rows)
    print(f"\nPatients with >= {MIN_EVENTS} events: {len(pp)}")
    if len(pp):
        print(pp[["patient_id", "design", "n", "slope_smb", "slope_basal_x", "slope_bolus"]]
              .sort_values(["design", "slope_smb"]).to_string(index=False))

    summary = []
    print("\n=== Per-design SMB-channel slope distribution (70-100 no-carb) ===")
    for d, sub in pp.groupby("design"):
        sl = sub["slope_smb"].values
        if len(sl) == 0:
            continue
        n_pos = int((sl > 0).sum())
        n_neg = int((sl < 0).sum())
        bt = binomtest(n_pos, len(sl), p=0.5, alternative="two-sided") if (n_pos + n_neg) > 0 else None
        print(f"  {d} (n_pat={len(sl)}) median={np.median(sl):+.4f} "
              f"mean={np.mean(sl):+.4f} ({n_pos}+/{n_neg}-) "
              f"sign_p={bt.pvalue if bt else float('nan'):.3g}")
        summary.append({"design": d, "n_pat": int(len(sl)),
                        "smb_median": float(np.median(sl)),
                        "smb_mean": float(np.mean(sl)),
                        "n_pos": n_pos, "n_neg": n_neg,
                        "sign_p": float(bt.pvalue) if bt else None,
                        "smb_slopes_sorted": sorted(sl.round(4).tolist())})

    mwu_out = {}
    for (a_d, b_d) in [("Loop_AB_ON", "oref1"), ("oref1", "Loop_AB_OFF"),
                       ("Loop_AB_ON", "Loop_AB_OFF")]:
        a = pp[pp.design == a_d]["slope_smb"].values
        b = pp[pp.design == b_d]["slope_smb"].values
        if len(a) >= 3 and len(b) >= 3:
            mw_two = stats.mannwhitneyu(a, b, alternative="two-sided")
            print(f"\n  MWU {a_d} vs {b_d}: U={mw_two.statistic:.1f} p={mw_two.pvalue:.4g}")
            mwu_out[f"{a_d}_vs_{b_d}"] = {"U": float(mw_two.statistic),
                                          "p_two_sided": float(mw_two.pvalue),
                                          "a_n": len(a), "b_n": len(b)}

    out = {
        "scope": "Per-patient SMB-channel velocity-coupling at 70-100 no-carb sweet spot",
        "band": [BAND_LO, BAND_HI],
        "n_events": int(len(ev)),
        "min_events_per_patient": MIN_EVENTS,
        "per_patient": pp.to_dict(orient="records"),
        "per_design_summary": summary,
        "mwu_smb_channel": mwu_out,
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2971] {OUT}")


if __name__ == "__main__":
    main()
