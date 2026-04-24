"""EXP-2964 - SMB-vs-basal decomposition of velocity-coupling at PP.

EXP-2960 measured TOTAL insulin coupling. This decomposes per-design
into bolus / SMB / basal-excess components, then fits per-design
slopes for each. Hypothesis: oref1's coupling driven primarily by
SMB+UAM, Loop AB ON's by AB user-bolus + scaled basal modulation,
Loop AB OFF and oref0 by basal modulation alone.

Maps directly to controller code-level levers for AID authors.

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
OUT = REPO / "externals" / "experiments" / "exp-2964_summary.json"

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
            xm = xs.mean(); ym = ys.mean()
            denom = float(np.sum((xs - xm) ** 2))
            if denom <= 0:
                continue
            vel = float(np.sum((xs - xm) * (ys - ym)) / denom)
            rows.append({
                "patient_id": pid, "design": d,
                "carbs_g": float(carbs[i]),
                "bg_entry": float(bg[i]),
                "vel_30": vel,
                "ins_60_bolus": float(bolus[i:i + INS_WIN].sum()),
                "ins_60_smb": float(smb[i:i + INS_WIN].sum()),
                "ins_60_basal_excess": float(basal_x[i:i + INS_WIN].sum()),
            })

    ev = pd.DataFrame(rows)
    ev["ins_60_total"] = ev["ins_60_bolus"] + ev["ins_60_smb"] + ev["ins_60_basal_excess"]
    print(f"Total meal events: {len(ev):,}")

    from scipy import stats

    print("\n=== Component contributions to mean ins_60_total ===")
    comp = ev.groupby("design").agg(
        bolus=("ins_60_bolus", "mean"),
        smb=("ins_60_smb", "mean"),
        basal_x=("ins_60_basal_excess", "mean"),
    )
    comp["total"] = comp.sum(axis=1)
    comp["bolus_pct"] = (comp["bolus"] / comp["total"] * 100).round(1)
    comp["smb_pct"] = (comp["smb"] / comp["total"] * 100).round(1)
    comp["basal_x_pct"] = (comp["basal_x"] / comp["total"] * 100).round(1)
    print(comp.round(3).to_string())

    print("\n=== Per-component velocity-coupling slopes (U per mg/dL/min) ===")
    out_rows = []
    for d, sub in ev.groupby("design"):
        if len(sub) < 30:
            continue
        comps = {}
        for label, col in [("bolus", "ins_60_bolus"),
                           ("smb", "ins_60_smb"),
                           ("basal_excess", "ins_60_basal_excess"),
                           ("total", "ins_60_total")]:
            sl, _, _, p, se = stats.linregress(sub["vel_30"], sub[col])
            comps[label] = {
                "slope": float(sl), "se": float(se),
                "ci_lo": float(sl - 1.96 * se),
                "ci_hi": float(sl + 1.96 * se),
                "p": float(p),
            }
        # decomposition % of total slope
        total_slope = comps["total"]["slope"]
        for label in ("bolus", "smb", "basal_excess"):
            comps[label]["pct_of_total_slope"] = (
                100.0 * comps[label]["slope"] / total_slope
                if abs(total_slope) > 1e-9 else None
            )
        print(f"\n  {d} (n={len(sub)})  TOTAL slope = {total_slope:+.4f}")
        for label in ("bolus", "smb", "basal_excess"):
            c = comps[label]
            pct = c["pct_of_total_slope"]
            pct_s = f"{pct:+.0f}%" if pct is not None else "n/a"
            print(f"    {label:>14}: {c['slope']:+.4f}  "
                  f"95%CI [{c['ci_lo']:+.4f},{c['ci_hi']:+.4f}]  "
                  f"({pct_s} of total)")
        out_rows.append({"design": d, "n": int(len(sub)), "components": comps})

    out = {
        "scope": "SMB-vs-basal velocity-coupling decomposition at PP",
        "n_events": int(len(ev)),
        "per_design_component_means": comp.reset_index().round(3).to_dict(orient="records"),
        "per_design_component_slopes": out_rows,
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2964] {OUT}")


if __name__ == "__main__":
    main()
