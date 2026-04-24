"""EXP-2959 - Per-patient empirical insulin action curve peak estimation.

For each patient with >= 30 sustained-high events, fit per-patient
peak in {45, 60, 75, 90, 105} (DIA fixed at 300) that minimises
residual variance of bg_delta predicted by synth_iob_entry. Compare
distribution by design (Mann-Whitney across designs).

Hypothesis check: do oref1 patients have systematically different
empirical peaks than Loop?  If yes, that may explain part of the
between-design iob_delta gap observed in EXP-2944/2950.

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
OUT = REPO / "externals" / "experiments" / "exp-2959_summary.json"

LOOP_AB_OFF = {"a", "f"}
LOOP_AB_ON = {"c", "d", "e", "g", "i"}
OREF0_PATS = {"odc-74077367", "odc-86025410", "odc-96254963"}

PEAK_GRID = [45.0, 60.0, 75.0, 90.0, 105.0]
DIA_MIN = 300.0


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


def iob_remaining(elapsed_min, peak):
    t = np.asarray(elapsed_min, dtype=float)
    out = np.ones_like(t)
    pre = t < peak
    out[pre] = 1.0 - 0.5 * (t[pre] / peak) ** 2
    post = (t >= peak) & (t < DIA_MIN)
    out[post] = 0.5 * (1.0 - (t[post] - peak) / (DIA_MIN - peak))
    out[t >= DIA_MIN] = 0.0
    return out


def synth_iob(events_t_min, events_u, eval_t, peak):
    if len(events_t_min) == 0:
        return 0.0
    elapsed = eval_t - events_t_min
    elapsed = elapsed[elapsed >= 0]
    units = events_u[:len(elapsed)]
    return float(np.sum(units * iob_remaining(elapsed, peak)))


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

    LOOKBACK_CELLS = int(DIA_MIN) // 5
    OUT_WIN = 12

    # Build sustained-high event table once with raw event arrays
    rows = []
    for pid, sub in g.groupby("patient_id"):
        d = design_of(pid, pid_to_lin.get(pid, ""))
        if d is None:
            continue
        sub = sub.sort_values("time").reset_index(drop=True)
        bg = sub["glucose"].values
        bg_prev = sub["glucose"].shift(1).values
        bg_max_pre = sub["glucose"].shift(1).rolling(6, min_periods=1).max().values
        carbs_pre = sub["carbs"].fillna(0).shift(1).rolling(6, min_periods=1).sum().fillna(0).values
        carbs = sub["carbs"].fillna(0).values
        ins_evt = sub["insulin_event"].values
        n = len(sub)
        for i in range(LOOKBACK_CELLS, n - OUT_WIN):
            if not (bg[i] >= 180 and bg_prev[i] < 180 and bg_max_pre[i] < 180
                    and carbs_pre[i] == 0
                    and carbs[i:i + OUT_WIN].sum() == 0):
                continue
            past_idx = np.arange(i - LOOKBACK_CELLS, i + 1)
            evt_u = ins_evt[past_idx]
            mask = evt_u > 1e-4
            if mask.any():
                evt_t = -(i - past_idx[mask]) * 5.0
                evt_u_m = evt_u[mask]
            else:
                evt_t = np.array([])
                evt_u_m = np.array([])
            rec = {
                "patient_id": pid, "design": d,
                "bg_entry": float(bg[i]),
                "bg_delta": float(bg[i + OUT_WIN] - bg[i]),
                "evt_t": evt_t.tolist(),
                "evt_u": evt_u_m.tolist(),
            }
            rows.append(rec)

    print(f"Total sustained-high events: {len(rows):,}")

    # Group by patient and fit best peak
    per_pat = []
    by_pid = {}
    for r in rows:
        by_pid.setdefault(r["patient_id"], []).append(r)

    for pid, recs in by_pid.items():
        if len(recs) < 30:
            continue
        d = recs[0]["design"]
        # For each peak candidate compute per-event synth_iob, regress
        # bg_delta ~ synth_iob; pick peak with min RSS.
        rss_by_peak = {}
        for peak in PEAK_GRID:
            iob = np.array([synth_iob(np.array(r["evt_t"]), np.array(r["evt_u"]), 0.0, peak)
                            for r in recs])
            y = np.array([r["bg_delta"] for r in recs])
            if iob.std() < 1e-6:
                rss_by_peak[peak] = float(np.var(y) * len(y))
                continue
            X = np.column_stack([iob, np.ones(len(iob))])
            beta, *_ = np.linalg.lstsq(X, y, rcond=None)
            resid = y - X @ beta
            rss_by_peak[peak] = float(np.sum(resid ** 2))
        best_peak = min(rss_by_peak, key=rss_by_peak.get)
        # Total variance baseline (intercept only)
        y = np.array([r["bg_delta"] for r in recs])
        rss0 = float(np.sum((y - y.mean()) ** 2))
        per_pat.append({
            "patient_id": pid, "design": d, "n_events": len(recs),
            "best_peak": best_peak,
            "rss_at_best": rss_by_peak[best_peak],
            "rss_at_75": rss_by_peak[75.0],
            "rss_intercept": rss0,
            "improve_pct_vs_75": 100.0 * (rss_by_peak[75.0] - rss_by_peak[best_peak]) / max(rss0, 1e-9),
            **{f"rss_{int(p)}": rss_by_peak[p] for p in PEAK_GRID},
        })

    pp = pd.DataFrame(per_pat)
    print(f"\nPatients with >=30 events: {len(pp)}")
    if len(pp) == 0:
        print("Insufficient events; aborting.")
        return
    print("\n=== Per-patient best peak ===")
    print(pp[["patient_id", "design", "n_events", "best_peak",
              "improve_pct_vs_75"]].sort_values("design").to_string(index=False))

    print("\n=== Best-peak distribution by design ===")
    print(pp.groupby("design").agg(
        n=("best_peak", "size"),
        peak_median=("best_peak", "median"),
        peak_mean=("best_peak", "mean"),
        peak_min=("best_peak", "min"),
        peak_max=("best_peak", "max"),
    ).round(2).to_string())

    # Mann-Whitney pairwise across designs
    from scipy import stats
    print("\n=== Pairwise Mann-Whitney on best_peak ===")
    designs = sorted(pp.design.unique())
    for i in range(len(designs)):
        for j in range(i + 1, len(designs)):
            a = pp[pp.design == designs[i]]["best_peak"].values
            b = pp[pp.design == designs[j]]["best_peak"].values
            if len(a) >= 2 and len(b) >= 2:
                u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
                print(f"  {designs[i]:14s} vs {designs[j]:14s}: "
                      f"medians {np.median(a):.0f}/{np.median(b):.0f}, p={p:.3g}")

    out = {
        "scope": "per-patient empirical IOB action-curve peak fit",
        "peak_grid": PEAK_GRID, "DIA_min": DIA_MIN,
        "n_patients_qualified": int(len(pp)),
        "by_design": pp.groupby("design").agg(
            n=("best_peak", "size"),
            peak_median=("best_peak", "median"),
            peak_mean=("best_peak", "mean"),
        ).reset_index().to_dict(orient="records"),
        "per_patient": pp.to_dict(orient="records"),
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2959] {OUT}")


if __name__ == "__main__":
    main()
