"""EXP-2923 - Cross-design fasted vs post-prandial dawn-hyper.

Promoted from inline analysis. Same fasted (>=300 min) /
post-prandial (<=180 min) split as EXP-2922, applied across
all three lineages.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
SIMP = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = REPO / "externals" / "experiments" / "exp-2923_summary.json"

HYPER = 250


def main() -> None:
    simp = pd.read_parquet(SIMP, columns=["patient_id", "lineage"])
    by_lin = {lin: set(simp[simp.lineage == lin]["patient_id"]) for lin in
              ["Loop (iOS)", "oref1 (modern)", "oref0 (legacy)"]}
    all_pids = set().union(*by_lin.values())

    g = pd.read_parquet(GRID, columns=["patient_id", "time", "glucose", "time_since_carb_min"])
    g = g[g.patient_id.isin(all_pids)].dropna(subset=["glucose"])
    g["hour"] = g["time"].dt.hour
    g["state"] = np.where(g.time_since_carb_min >= 300, "FASTED",
                          np.where(g.time_since_carb_min <= 180, "PP", "MID"))
    g = g[g.state != "MID"]

    short = {"Loop (iOS)": "Loop", "oref1 (modern)": "oref1", "oref0 (legacy)": "oref0"}
    g["lineage"] = g.patient_id.map(
        lambda p: next(short[lin] for lin, s in by_lin.items() if p in s)
    )

    rows = []
    for (pid, lin, st, hr), sub in g.groupby(["patient_id", "lineage", "state", "hour"]):
        if len(sub) < 6:
            continue
        rows.append({"patient_id": pid, "lineage": lin, "state": st, "hour": int(hr),
                     "frac_hyper": float((sub.glucose > HYPER).mean())})
    pat = pd.DataFrame(rows)

    out = []
    for lin in ["Loop", "oref1", "oref0"]:
        for st in ["FASTED", "PP"]:
            sub = pat[(pat.lineage == lin) & (pat.state == st)]
            if sub.empty:
                continue
            cell = sub.groupby("hour").apply(
                lambda d: d.groupby("patient_id")["frac_hyper"].mean().mean()
            )
            out.append({
                "lineage": lin, "state": st,
                "n": int(sub.patient_id.nunique()),
                "peak_hr": int(cell.idxmax()),
                "peak_pct": float(cell.max()) * 100,
                "hr3_pct": float(cell.get(3, 0)) * 100,
                "hr4_pct": float(cell.get(4, 0)) * 100,
            })
    summary = {"scope": "fasted vs PP across all lineages; AID-author audience", "rows": out}
    OUT.write_text(json.dumps(summary, indent=2))
    for r in out:
        print(f"  {r['lineage']:6s} {r['state']:7s} n={r['n']}: peak hr {r['peak_hr']:02d} = {r['peak_pct']:5.2f}%  | hr3={r['hr3_pct']:5.2f}%  hr4={r['hr4_pct']:5.2f}%")
    print(f"[exp-2923] {OUT}")


if __name__ == "__main__":
    main()
