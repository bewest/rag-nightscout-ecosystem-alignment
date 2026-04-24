"""EXP-2957 - Action-curve sensitivity sweep.

EXP-2950/2953/2954 used a single uniform action-curve (peak 75 min,
DIA 300 min). Does the cross-design IOB-age conclusion depend on
that specific choice?

Sweeps peak in {60, 75, 90} and DIA in {240, 300, 360} (9 combos);
recomputes the sustained-high mechanism metric (iob_delta:
oref1 vs Loop_AB_ON) for each.

If the sign and significance of the iob_delta gap are stable across
all 9 combos, the EXP-2950 conclusion is robust to action-curve
parameterisation — addresses a natural reviewer objection.

Scope: AID-author / methodological audit.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
SIMP = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = REPO / "externals" / "experiments" / "exp-2957_summary.json"

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


def make_curves(peak, dia):
    def iob_remaining(t):
        t = np.asarray(t, dtype=float)
        out = np.ones_like(t)
        pre = t < peak
        out[pre] = 1.0 - 0.5 * (t[pre] / peak) ** 2
        post = (t >= peak) & (t < dia)
        out[post] = 0.5 * (1.0 - (t[post] - peak) / (dia - peak))
        out[t >= dia] = 0.0
        return out
    return iob_remaining


def synth_iob(events_t_min, events_u, eval_t, iob_fn):
    if len(events_t_min) == 0:
        return 0.0
    elapsed = eval_t - events_t_min
    elapsed = elapsed[elapsed >= 0]
    units = events_u[:len(elapsed)]
    return float(np.sum(units * iob_fn(elapsed)))


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

    # Sustained-high event detection (mirrors EXP-2944/2950 pattern):
    # bg crosses above 200 with no recent carbs; track over 60min for iob_delta
    PRE_CARB_CELLS = 24  # 120 min
    POST_CELLS = 12      # 60 min
    PEAKS = [60, 75, 90]
    DIAS = [240, 300, 360]
    MAX_DIA = max(DIAS)
    LOOKBACK_CELLS = MAX_DIA // 5

    events = []
    for pid, sub in g.groupby("patient_id"):
        d = design_of(pid, pid_to_lin.get(pid, ""))
        if d is None:
            continue
        sub = sub.sort_values("time").reset_index(drop=True)
        bg = sub["glucose"].values
        bg_prev = sub["glucose"].shift(1).values
        carbs_pre = sub["carbs"].fillna(0).shift(1).rolling(PRE_CARB_CELLS, min_periods=1).sum().fillna(0).values
        ins_evt = sub["insulin_event"].values
        n = len(sub)
        for i in range(LOOKBACK_CELLS, n - POST_CELLS):
            if not (bg[i] > 200 and bg_prev[i] <= 200 and carbs_pre[i] == 0):
                continue
            past_idx = np.arange(i - LOOKBACK_CELLS, i + POST_CELLS + 1)
            evt_u = ins_evt[past_idx]
            mask = evt_u > 1e-4
            if mask.any():
                evt_t_rel_i = -(i - past_idx[mask]) * 5.0
                evt_u_m = evt_u[mask]
            else:
                evt_t_rel_i = np.array([])
                evt_u_m = np.array([])
            events.append({
                "pid": pid, "d": d, "evt_t": evt_t_rel_i, "evt_u": evt_u_m,
            })

    print(f"Sustained-high events: {len(events)}")

    from scipy import stats
    sweep = []
    for peak in PEAKS:
        for dia in DIAS:
            iob_fn = make_curves(peak, dia)
            deltas = {"oref1": [], "Loop_AB_ON": []}
            for ev in events:
                if ev["d"] not in deltas:
                    continue
                iob0 = synth_iob(ev["evt_t"], ev["evt_u"], 0.0, iob_fn)
                iob60 = synth_iob(ev["evt_t"], ev["evt_u"], 60.0, iob_fn)
                deltas[ev["d"]].append(iob60 - iob0)
            o = np.array(deltas["oref1"])
            l = np.array(deltas["Loop_AB_ON"])
            if len(o) == 0 or len(l) == 0:
                continue
            t, p = stats.ttest_ind(o, l, equal_var=False)
            sweep.append({
                "peak": peak, "dia": dia,
                "n_oref1": len(o), "n_loop_ab_on": len(l),
                "iob_delta_oref1_mean": float(o.mean()),
                "iob_delta_loop_ab_on_mean": float(l.mean()),
                "gap_oref1_minus_loop": float(o.mean() - l.mean()),
                "t": float(t), "p": float(p),
            })

    sw = pd.DataFrame(sweep)
    print("\n=== Sweep results: iob_delta gap (oref1 - Loop_AB_ON) ===")
    print("Negative gap = oref1 sheds faster than Loop (framework supported)")
    print(sw.to_string(index=False))

    n_neg = (sw["gap_oref1_minus_loop"] < 0).sum()
    n_sig = ((sw["gap_oref1_minus_loop"] < 0) & (sw["p"] < 0.05)).sum()
    print(f"\nCombinations with negative gap: {n_neg}/{len(sw)}")
    print(f"Combinations significant (p<0.05): {n_sig}/{len(sw)}")
    print(f"Median gap across sweep: {sw['gap_oref1_minus_loop'].median():.3f}")

    out = {
        "scope": "action-curve sensitivity sweep for IOB-age framework",
        "sweep": sw.to_dict(orient="records"),
        "n_neg_gap": int(n_neg),
        "n_sig": int(n_sig),
        "n_combos": int(len(sw)),
        "robust_to_curve_choice": bool(n_neg == len(sw) and n_sig >= len(sw) - 1),
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2957] {OUT}")


if __name__ == "__main__":
    main()
