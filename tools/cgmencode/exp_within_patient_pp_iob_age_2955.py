"""EXP-2955 - Within-patient validation of IOB-age framework at PP windows.

Cross-validates EXP-2954's gold-standard within-patient template
on the post-prandial (PP) channel. EXP-2946 found the IOB-timing
mechanism between designs at PP. EXP-2954 confirmed it within-patient
at hypo. Does it ALSO hold within-patient at PP?

Hypothesis: higher uniform action density at carb-onset (synth_act_entry)
should predict LOWER bg_peak within each patient — same biology as
hypo (active insulin opposes the rise) regardless of design.

Window definition: meal events (carbs >= 30 g), no carbs in prior 60min,
bg available 0-180min after onset. Outcome: bg_peak in [0, 180min].

Pipeline mirrors EXP-2954: per-patient regression + sign test.

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
OUT = REPO / "externals" / "experiments" / "exp-2955_summary.json"

LOOP_AB_OFF = {"a", "f"}
LOOP_AB_ON = {"c", "d", "e", "g", "i"}
OREF0_PATS = {"odc-74077367", "odc-86025410", "odc-96254963"}

PEAK_MIN = 75.0
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


def iob_remaining(t):
    t = np.asarray(t, dtype=float)
    out = np.ones_like(t)
    pre = t < PEAK_MIN
    out[pre] = 1.0 - 0.5 * (t[pre] / PEAK_MIN) ** 2
    post = (t >= PEAK_MIN) & (t < DIA_MIN)
    out[post] = 0.5 * (1.0 - (t[post] - PEAK_MIN) / (DIA_MIN - PEAK_MIN))
    out[t >= DIA_MIN] = 0.0
    return out


def activity_density(t):
    t = np.asarray(t, dtype=float)
    out = np.zeros_like(t)
    pre = t < PEAK_MIN
    out[pre] = t[pre] / (PEAK_MIN ** 2)
    post = (t >= PEAK_MIN) & (t < DIA_MIN)
    out[post] = 0.5 / (DIA_MIN - PEAK_MIN)
    return out


def synth_at(events_t_min, events_u, eval_t):
    if len(events_t_min) == 0:
        return 0.0, 0.0
    elapsed = eval_t - events_t_min
    elapsed = elapsed[elapsed >= 0]
    units = events_u[:len(elapsed)]
    return float(np.sum(units * iob_remaining(elapsed))), \
           float(np.sum(units * activity_density(elapsed)))


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
    FORWARD_CELLS = 36  # 180 min
    PRE_CARB_CELLS = 12  # 60 min
    rows = []

    for pid, sub in g.groupby("patient_id"):
        d = design_of(pid, pid_to_lin.get(pid, ""))
        if d is None:
            continue
        sub = sub.sort_values("time").reset_index(drop=True)
        carbs = sub["carbs"].fillna(0).values
        carbs_60_pre = sub["carbs"].fillna(0).shift(1).rolling(PRE_CARB_CELLS, min_periods=1).sum().fillna(0).values
        bg = sub["glucose"].values
        ins_evt = sub["insulin_event"].values
        n = len(sub)
        for i in range(LOOKBACK_CELLS, n - FORWARD_CELLS):
            if not (carbs[i] >= 30 and carbs_60_pre[i] == 0):
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
            iob_e, act_e = synth_at(evt_t, evt_u_m, 0.0)
            rows.append({
                "patient_id": pid, "design": d,
                "carbs_g": float(carbs[i]),
                "act_entry": act_e,
                "iob_entry": iob_e,
                "bg_entry": float(bg[i]),
                "bg_peak_180": float(np.nanmax(bg[i:i + FORWARD_CELLS])),
                "delta_peak": float(np.nanmax(bg[i:i + FORWARD_CELLS]) - bg[i]),
                "tar_180_pct": float((sub["glucose"].iloc[i:i + FORWARD_CELLS] > 180).mean()),
            })

    ev = pd.DataFrame(rows)
    print(f"Total PP meal events: {len(ev):,}")
    if len(ev) == 0:
        print("No events; aborting.")
        return

    # Normalise act_entry per gram of carbs to get carb-adjusted comparison
    # — but for the within-patient slope we let act_entry, carbs, bg_entry
    # all enter; here we use a single-predictor slope as in EXP-2954
    # for direct comparability, then ALSO report a multi-factor slope.
    from scipy import stats
    per_pat = []
    for pid, sub in ev.groupby("patient_id"):
        if len(sub) < 20 or sub["act_entry"].std() < 1e-5:
            continue
        # Single-predictor: act_entry → delta_peak (negative slope = framework supported)
        slope, intercept, r, p, se = stats.linregress(sub["act_entry"], sub["delta_peak"])
        # Multi-factor: residualise on carbs and bg_entry
        try:
            X = np.column_stack([sub["act_entry"], sub["carbs_g"], sub["bg_entry"], np.ones(len(sub))])
            beta, *_ = np.linalg.lstsq(X, sub["delta_peak"].values, rcond=None)
            slope_mf = float(beta[0])
        except Exception:
            slope_mf = np.nan
        per_pat.append({
            "patient_id": pid,
            "design": sub["design"].iloc[0],
            "n_events": len(sub),
            "slope_single": slope, "p_single": p,
            "slope_mf": slope_mf,
            "act_mean": sub["act_entry"].mean(),
            "delta_peak_mean": sub["delta_peak"].mean(),
        })
    pp = pd.DataFrame(per_pat)
    print(f"\nPatients with >=20 events: {len(pp)}")
    if len(pp) == 0:
        print("No qualified patients; aborting.")
        return

    print("\n=== Per-patient slope ===")
    print(pp.sort_values("design").to_string(index=False))

    from scipy.stats import binomtest
    for label, col in [("single-predictor slope", "slope_single"),
                       ("multi-factor slope (act|carbs,bg_entry)", "slope_mf")]:
        valid = pp[col].dropna()
        n_neg = (valid < 0).sum()
        bt = binomtest(int(n_neg), n=len(valid), p=0.5, alternative="greater")
        t, p_t = stats.ttest_1samp(valid, 0.0)
        print(f"\n=== {label} ===")
        print(f"  n_pat={len(valid)}, n_neg={n_neg}, sign-test p={bt.pvalue:.3g}")
        print(f"  median={valid.median():+.2f}, mean={valid.mean():+.2f}, t-test p={p_t:.3g}")

    print("\n=== By design (single-predictor) ===")
    for dlab, sub in pp.groupby("design"):
        n_neg_d = (sub.slope_single < 0).sum()
        print(f"  {dlab:14s}: n={len(sub)}, median slope {sub.slope_single.median():+.2f}, "
              f"{n_neg_d}/{len(sub)} negative")

    out = {
        "scope": "within-patient validation of IOB-age framework at PP",
        "outcome": "delta_peak (bg_peak_180 - bg_entry)",
        "predictor": "synth_act_entry (uniform biexp peak75/DIA300)",
        "n_events": int(len(ev)),
        "n_patients_qualified": int(len(pp)),
        "single_pred_n_neg": int((pp.slope_single < 0).sum()),
        "single_pred_median_slope": float(pp.slope_single.median()),
        "single_pred_binomial_p": float(binomtest(
            int((pp.slope_single < 0).sum()), n=len(pp), p=0.5, alternative="greater").pvalue),
        "mf_n_neg": int((pp.slope_mf.dropna() < 0).sum()),
        "mf_median_slope": float(pp.slope_mf.median()),
        "per_patient": pp.to_dict(orient="records"),
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2955] {OUT}")


if __name__ == "__main__":
    main()
