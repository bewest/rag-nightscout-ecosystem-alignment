"""EXP-2947 - hypo-side IOB pattern: does early IOB decay distinguish designs?

EXP-2925 confirmed Pareto-dominance: oref1 has BOTH lower TAR AND
lower TBR vs Loop. EXP-2944/2946 established IOB timing distinguishes
recovery and PP. This tests the hypo side: do designs differ in how
fast IOB decays in the run-up to a hypo?

Anchor: BG crosses 80 from above (descending threshold), prior 30min
all >80, no carbs in 60min before (carb-isolation).

Window: 60 min FORWARD (does hypo materialise; if so how deep) and
60 min BACKWARD (was IOB falling fast enough?).

Scope: AID-author audience. Hypo-prevention timing.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
SIMP = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = REPO / "externals" / "experiments" / "exp-2947_summary.json"

DESCEND = 80.0
PRE_QUIET_MIN = 30
CARB_GUARD_MIN = 60
WIN_FWD_MIN = 60
WIN_BWD_MIN = 60

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

    cols = ["patient_id", "time", "glucose", "carbs", "iob",
            "actual_basal_rate", "scheduled_basal_rate"]
    g = pd.read_parquet(GRID, columns=cols)
    g = g[g.patient_id.isin(set(simp.patient_id))].dropna(subset=["glucose", "iob"])
    g = g.sort_values(["patient_id", "time"]).reset_index(drop=True)

    rows = []
    n_fwd = WIN_FWD_MIN // 5
    n_bwd = WIN_BWD_MIN // 5
    for pid, sub in g.groupby("patient_id"):
        d = design_of(pid, pid_to_lin.get(pid, ""))
        if d is None:
            continue
        sub = sub.sort_values("time").reset_index(drop=True)
        bg_prev = sub["glucose"].shift(1)
        bg_min_30 = sub["glucose"].shift(1).rolling(window=PRE_QUIET_MIN // 5, min_periods=1).min()
        carbs_60_pre = sub["carbs"].shift(1).rolling(window=CARB_GUARD_MIN // 5, min_periods=1).sum().fillna(0)
        ents = sub.index[(sub["glucose"] <= DESCEND) & (bg_prev > DESCEND) &
                         (bg_min_30 > DESCEND) & (carbs_60_pre == 0)]
        for ent in ents:
            if ent < n_bwd or ent + n_fwd >= len(sub):
                continue
            fwd = sub.iloc[ent:ent + n_fwd]
            bwd = sub.iloc[ent - n_bwd:ent]
            if fwd["carbs"].fillna(0).sum() > 0 or bwd["carbs"].fillna(0).sum() > 0:
                continue  # carb-isolated entire ±60min
            bg_fwd = fwd["glucose"].values
            iob_bwd = bwd["iob"].values
            iob_fwd = fwd["iob"].values
            sched = bwd["scheduled_basal_rate"].fillna(0).mean()
            actual = bwd["actual_basal_rate"].fillna(0).mean()
            cut_frac_bwd = float((bwd["actual_basal_rate"].fillna(0) <
                                  bwd["scheduled_basal_rate"].fillna(0) - 1e-6).mean())
            rows.append({
                "patient_id": pid, "design": d,
                "iob_at_entry": float(iob_bwd[-1]) if len(iob_bwd) else np.nan,
                "iob_60min_before": float(iob_bwd[0]) if len(iob_bwd) else np.nan,
                "iob_decay_60": (float(iob_bwd[-1] - iob_bwd[0])) if len(iob_bwd) else np.nan,
                "iob_decay_fwd_60": float(iob_fwd[-1] - iob_fwd[0]),
                "bg_min_60": float(bg_fwd.min()),
                "tbr_70_pct": float((bg_fwd < 70).mean()),
                "tbr_54_pct": float((bg_fwd < 54).mean()),
                "basal_cut_frac_pre60": cut_frac_bwd,
                "basal_actual_pre60": float(actual),
                "basal_sched_pre60": float(sched),
            })

    ev = pd.DataFrame(rows)
    print(f"Total descend-events (carb-isolated ±60min): {len(ev):,}")

    print("\n=== Per-design (descend at BG=80, no carbs ±60min) ===")
    summary = ev.groupby("design").agg(
        n=("bg_min_60", "size"),
        iob_at_entry=("iob_at_entry", "mean"),
        iob_decay_pre60=("iob_decay_60", "mean"),
        iob_decay_fwd60=("iob_decay_fwd_60", "mean"),
        bg_min_60=("bg_min_60", "mean"),
        tbr_70_pct=("tbr_70_pct", "mean"),
        tbr_54_pct=("tbr_54_pct", "mean"),
        basal_cut_frac=("basal_cut_frac_pre60", "mean"),
    ).round(3)
    print(summary.to_string())

    print("\n=== Loop_AB_ON vs oref1 ===")
    for col in ["iob_at_entry", "iob_decay_60", "iob_decay_fwd_60",
                "bg_min_60", "tbr_70_pct", "tbr_54_pct", "basal_cut_frac_pre60"]:
        a = ev[ev.design == "Loop_AB_ON"][col].dropna().values
        b = ev[ev.design == "oref1"][col].dropna().values
        if len(a) > 0 and len(b) > 0:
            print(f"  {col:25s}: Loop {a.mean():+.3f} | oref1 {b.mean():+.3f} | Δ {a.mean()-b.mean():+.3f}")

    out = {
        "scope": "hypo-side IOB decay timing for descending BG events",
        "n_events": int(len(ev)),
        "by_design": summary.reset_index().to_dict(orient="records"),
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2947] {OUT}")


if __name__ == "__main__":
    main()
