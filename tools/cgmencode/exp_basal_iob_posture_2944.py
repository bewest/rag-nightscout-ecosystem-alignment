"""EXP-2944 - basal-channel + true-IOB posture during sustained-high windows.

Last remaining in-grid measurable mechanism channels for the
Loop_AB_ON vs oref1 +21pp recovery gap:
  - true `iob` column (vs the EXP-2941 SMB-sum proxy)
  - `net_basal` deviation from scheduled (basal-channel posture)
  - cumulative net_basal within window (basal contribution to recovery)
  - `actual_basal_rate` and `loop_enacted_rate` profiles

Reuse EXP-2937 carb-isolated event extraction.

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
OUT = REPO / "externals" / "experiments" / "exp-2944_summary.json"

HIGH = 180.0
WINDOW_MIN = 60
PRE_QUIET_MIN = 30
CARB_GUARD_MIN = 60

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

    cols = ["patient_id", "time", "glucose", "carbs", "bolus_smb",
            "iob", "net_basal", "actual_basal_rate", "scheduled_basal_rate"]
    g = pd.read_parquet(GRID, columns=cols)
    g = g[g.patient_id.isin(set(simp.patient_id))].dropna(subset=["glucose"])
    g = g.sort_values(["patient_id", "time"]).reset_index(drop=True)

    # Coverage check
    print("=== Column non-null fraction by design ===")
    cov = []
    for pid, sub in g.groupby("patient_id"):
        d = design_of(pid, pid_to_lin.get(pid, ""))
        if d is None:
            continue
        for c in ["iob", "net_basal", "actual_basal_rate"]:
            cov.append({"design": d, "col": c, "frac": float(sub[c].notna().mean())})
    cov_df = pd.DataFrame(cov).groupby(["design", "col"])["frac"].mean().unstack().round(2)
    print(cov_df.to_string())

    rec_rows = []
    n_cells = WINDOW_MIN // 5
    for pid, sub in g.groupby("patient_id"):
        d = design_of(pid, pid_to_lin.get(pid, ""))
        if d is None:
            continue
        sub = sub.sort_values("time").reset_index(drop=True)
        bg_prev = sub["glucose"].shift(1)
        bg_max_30 = sub["glucose"].shift(1).rolling(window=PRE_QUIET_MIN // 5, min_periods=1).max()
        carbs_60 = sub["carbs"].shift(1).rolling(window=CARB_GUARD_MIN // 5, min_periods=1).sum().fillna(0)
        ents = sub.index[(sub["glucose"] > HIGH) & (bg_prev <= HIGH) &
                         (bg_max_30 <= HIGH) & (carbs_60 == 0)]
        for ent_idx in ents:
            win = sub.iloc[ent_idx:ent_idx + n_cells]
            if len(win) < n_cells or win["carbs"].fillna(0).sum() > 0:
                continue
            bg = win["glucose"].values
            iob_start = float(win["iob"].iloc[0]) if pd.notna(win["iob"].iloc[0]) else np.nan
            iob_end = float(win["iob"].iloc[-1]) if pd.notna(win["iob"].iloc[-1]) else np.nan
            iob_delta = (iob_end - iob_start) if pd.notna(iob_start) and pd.notna(iob_end) else np.nan
            nb = win["net_basal"].fillna(0).values  # U/h deviation
            nb_mean = float(nb.mean())
            nb_cum_units = float(nb.sum() / 12)  # U integrated over 60min in 5-min cells
            actual = win["actual_basal_rate"].fillna(0).values
            scheduled = win["scheduled_basal_rate"].fillna(0).values
            cut_frac = float((actual < scheduled - 1e-6).mean()) if scheduled.max() > 0 else np.nan
            rec_rows.append({
                "patient_id": pid, "design": d,
                "bg_start": float(bg[0]), "bg_end": float(bg[-1]), "bg_peak": float(bg.max()),
                "decline_per_min": float((bg[0] - bg[-1]) / WINDOW_MIN),
                "recovered": bool(bg[-1] < HIGH),
                "iob_start": iob_start, "iob_end": iob_end, "iob_delta": iob_delta,
                "net_basal_mean_uph": nb_mean,
                "net_basal_cum_units": nb_cum_units,
                "basal_cut_frac": cut_frac,
            })

    ev = pd.DataFrame(rec_rows)
    print(f"\nTotal events: {len(ev):,}")

    print("\n=== Per-design means ===")
    summary = ev.groupby("design").agg(
        n_events=("recovered", "size"),
        recovered=("recovered", "mean"),
        bg_start=("bg_start", "mean"),
        iob_start=("iob_start", "mean"),
        iob_delta=("iob_delta", "mean"),
        net_basal_mean=("net_basal_mean_uph", "mean"),
        net_basal_cum=("net_basal_cum_units", "mean"),
        basal_cut_frac=("basal_cut_frac", "mean"),
    ).round(3)
    print(summary.to_string())

    print("\n=== Loop_AB_ON vs oref1 head-to-head (the 21pp gap row) ===")
    for col in ["iob_start", "iob_delta", "net_basal_mean_uph",
                "net_basal_cum_units", "basal_cut_frac"]:
        a = ev[ev.design == "Loop_AB_ON"][col].dropna().values
        b = ev[ev.design == "oref1"][col].dropna().values
        if len(a) > 0 and len(b) > 0:
            print(f"  {col:25s}: Loop {a.mean():+.3f} | oref1 {b.mean():+.3f} | Δ {a.mean()-b.mean():+.3f}")

    # Within-design recovery split by IOB tertile
    print("\n=== Recovery by iob_start tertile (within design) ===")
    for d in ["Loop_AB_ON", "oref1"]:
        sub = ev[(ev.design == d) & ev["iob_start"].notna()].copy()
        if len(sub) < 30:
            continue
        sub["tile"] = pd.qcut(sub["iob_start"], 3, labels=["lo", "mid", "hi"], duplicates="drop")
        for t, g_ in sub.groupby("tile", observed=True):
            print(f"  {d:12s} {str(t):3s} (n={len(g_):4d}): iob_start={g_['iob_start'].mean():.2f}  recovered={g_['recovered'].mean():.3f}")

    # Within-design recovery split by net_basal_cum (basal posture during window)
    print("\n=== Recovery by within-window net_basal_cum tertile ===")
    for d in ["Loop_AB_ON", "oref1"]:
        sub = ev[ev.design == d].copy()
        if len(sub) < 30:
            continue
        sub["tile"] = pd.qcut(sub["net_basal_cum_units"], 3, labels=["lo", "mid", "hi"], duplicates="drop")
        for t, g_ in sub.groupby("tile", observed=True):
            print(f"  {d:12s} {str(t):3s} (n={len(g_):4d}): net_basal_cum={g_['net_basal_cum_units'].mean():+.3f}U  recovered={g_['recovered'].mean():.3f}")

    out = {
        "scope": "true-IOB and basal-channel posture during sustained-high recovery",
        "n_events": int(len(ev)),
        "by_design": summary.reset_index().to_dict(orient="records"),
        "iob_coverage": cov_df.to_dict(),
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2944] {OUT}")


if __name__ == "__main__":
    main()
