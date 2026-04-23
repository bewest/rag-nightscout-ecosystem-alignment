"""EXP-2946 - IOB-timing mechanism validation in post-prandial windows.

EXP-2944 established IOB-delta is the recovery mechanism for
sustained-high carb-isolated windows. This experiment tests whether
the same lever explains the PP TIR gap (EXP-2929: 53% closure by
autobolus; +21pp residual oref1 vs Loop_AB_ON).

Hypothesis: in PP windows, oref1 also reaches IOB peak earlier
relative to BG response, producing higher TIR. Tests:
  - iob_start at meal time (~equal expected)
  - time-to-iob-peak within 0-180min PP window
  - iob value at BG peak time
  - per-design TIR within PP window

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
OUT = REPO / "externals" / "experiments" / "exp-2946_summary.json"

PP_WINDOW_MIN = 180
MIN_CARBS = 20  # only meaningful meals

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

    cols = ["patient_id", "time", "glucose", "carbs", "iob", "bolus_smb"]
    g = pd.read_parquet(GRID, columns=cols)
    g = g[g.patient_id.isin(set(simp.patient_id))].dropna(subset=["glucose", "iob"])
    g = g.sort_values(["patient_id", "time"]).reset_index(drop=True)

    rows = []
    n_cells = PP_WINDOW_MIN // 5
    for pid, sub in g.groupby("patient_id"):
        d = design_of(pid, pid_to_lin.get(pid, ""))
        if d is None:
            continue
        sub = sub.sort_values("time").reset_index(drop=True)
        # Quiet-pre filter: no carbs in 3h before
        carbs_3h = sub["carbs"].shift(1).rolling(window=36, min_periods=1).sum().fillna(0)
        meals = sub.index[(sub["carbs"].fillna(0) >= MIN_CARBS) & (carbs_3h == 0)]
        for m in meals:
            win = sub.iloc[m:m + n_cells]
            if len(win) < n_cells:
                continue
            # No second meal within window
            if win["carbs"].iloc[1:].fillna(0).sum() > 0:
                continue
            iob = win["iob"].values
            bg = win["glucose"].values
            t = np.arange(len(iob)) * 5
            iob_peak_idx = int(np.argmax(iob))
            bg_peak_idx = int(np.argmax(bg))
            tir_pct = float(((bg >= 70) & (bg <= 180)).mean())
            tar_pct = float((bg > 180).mean())
            rows.append({
                "patient_id": pid, "design": d,
                "carbs": float(sub["carbs"].iloc[m]),
                "iob_start": float(iob[0]),
                "iob_peak": float(iob.max()),
                "iob_peak_min": int(t[iob_peak_idx]),
                "bg_start": float(bg[0]),
                "bg_peak": float(bg.max()),
                "bg_peak_min": int(t[bg_peak_idx]),
                "iob_at_bg_peak": float(iob[bg_peak_idx]),
                "iob_delta_60": float(iob[12] - iob[0]) if len(iob) >= 13 else np.nan,
                "tir_pct": tir_pct,
                "tar_pct": tar_pct,
            })

    ev = pd.DataFrame(rows)
    print(f"Total meals: {len(ev):,}")

    print("\n=== Per-design PP means (carbs >=20g, 3h quiet-pre, no overlap) ===")
    summary = ev.groupby("design").agg(
        n=("tir_pct", "size"),
        carbs=("carbs", "mean"),
        iob_start=("iob_start", "mean"),
        iob_peak=("iob_peak", "mean"),
        iob_peak_min=("iob_peak_min", "median"),
        iob_delta_60=("iob_delta_60", "mean"),
        bg_peak=("bg_peak", "mean"),
        bg_peak_min=("bg_peak_min", "median"),
        iob_at_bg_peak=("iob_at_bg_peak", "mean"),
        tir_pct=("tir_pct", "mean"),
        tar_pct=("tar_pct", "mean"),
    ).round(3)
    print(summary.to_string())

    print("\n=== Loop_AB_ON vs oref1 head-to-head ===")
    for col in ["iob_start", "iob_peak", "iob_peak_min", "iob_delta_60",
                "bg_peak_min", "iob_at_bg_peak", "tir_pct"]:
        a = ev[ev.design == "Loop_AB_ON"][col].dropna().values
        b = ev[ev.design == "oref1"][col].dropna().values
        if len(a) > 0 and len(b) > 0:
            print(f"  {col:20s}: Loop {a.mean():+.3f} | oref1 {b.mean():+.3f} | Δ {a.mean()-b.mean():+.3f}")

    # Critical: does IOB-peak-relative-to-BG-peak matter?
    print("\n=== IOB-peak vs BG-peak timing (lead/lag in min) ===")
    ev["iob_lead_bg_min"] = ev["iob_peak_min"] - ev["bg_peak_min"]
    for d, sub in ev.groupby("design"):
        print(f"  {d:12s} median: {sub['iob_lead_bg_min'].median():+.1f} min  (negative = IOB peaks BEFORE BG)")

    # Tertile: PP TIR by iob_delta_60
    print("\n=== TIR by iob_delta_60 tertile (within design) ===")
    for d in ["Loop_AB_ON", "oref1"]:
        sub = ev[(ev.design == d) & ev["iob_delta_60"].notna()].copy()
        if len(sub) < 30:
            continue
        sub["tile"] = pd.qcut(sub["iob_delta_60"], 3, labels=["lo", "mid", "hi"], duplicates="drop")
        for t, g_ in sub.groupby("tile", observed=True):
            print(f"  {d:12s} {str(t):3s} (n={len(g_):4d}): "
                  f"iob_delta_60={g_['iob_delta_60'].mean():+.2f}U  "
                  f"tir={g_['tir_pct'].mean():.3f}  bg_peak={g_['bg_peak'].mean():.0f}")

    out = {
        "scope": "IOB-timing mechanism validation in post-prandial windows",
        "n_meals": int(len(ev)),
        "by_design": summary.reset_index().to_dict(orient="records"),
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2946] {OUT}")


if __name__ == "__main__":
    main()
