"""EXP-2954 - Within-patient validation of IOB-age framework.

EXP-2950/2953 established between-design mechanism. This tests
within-patient: does higher uniform_act_entry predict deeper hypos
WITHIN each patient's event history, controlling for between-patient
heterogeneity?

If the IOB-age framework is real biology and not just a design-level
correlation, within-patient regression of bg_min ~ synth_act_entry
should yield consistently negative slopes across patients.

Pipeline mirrors EXP-2953 for hypo events; reuses uniform action-curve
re-derivation. Per-patient regressions; aggregate slope and significance.

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
OUT = REPO / "externals" / "experiments" / "exp-2954_summary.json"

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
    rows = []

    for pid, sub in g.groupby("patient_id"):
        d = design_of(pid, pid_to_lin.get(pid, ""))
        if d is None:
            continue
        sub = sub.sort_values("time").reset_index(drop=True)
        bg = sub["glucose"].values
        bg_prev = sub["glucose"].shift(1).values
        bg_min_30 = sub["glucose"].shift(1).rolling(6, min_periods=1).min().values
        carbs_60_pre = sub["carbs"].shift(1).rolling(12, min_periods=1).sum().fillna(0).values
        ins_evt = sub["insulin_event"].values
        n = len(sub)
        for i in range(LOOKBACK_CELLS, n - 12):
            if not (bg[i] <= 80 and bg_prev[i] > 80 and bg_min_30[i] > 80
                    and carbs_60_pre[i] == 0
                    and sub.iloc[i:i+12]["carbs"].fillna(0).sum() == 0):
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
                "act_entry": act_e,
                "iob_entry": iob_e,
                "bg_min_60": float(sub.iloc[i:i+12]["glucose"].min()),
                "tbr_54_pct": float((sub.iloc[i:i+12]["glucose"] < 54).mean()),
            })

    ev = pd.DataFrame(rows)
    print(f"Total hypo events: {len(ev):,}")

    # Per-patient regression: bg_min ~ act_entry
    from scipy import stats
    per_pat = []
    for pid, sub in ev.groupby("patient_id"):
        if len(sub) < 20 or sub["act_entry"].std() < 1e-5:
            continue
        slope, intercept, r, p, se = stats.linregress(sub["act_entry"], sub["bg_min_60"])
        per_pat.append({
            "patient_id": pid,
            "design": sub["design"].iloc[0],
            "n_events": len(sub),
            "slope_bg_per_act": slope,
            "r": r,
            "p": p,
            "act_mean": sub["act_entry"].mean(),
            "bg_min_mean": sub["bg_min_60"].mean(),
        })
    pp = pd.DataFrame(per_pat)
    print(f"\nPatients with >=20 events: {len(pp)}")

    print("\n=== Per-patient slope of bg_min ~ act_entry (negative = framework supported) ===")
    print(pp.sort_values("design").to_string(index=False))

    print("\n=== Direction summary ===")
    n_neg = (pp.slope_bg_per_act < 0).sum()
    n_neg_sig = ((pp.slope_bg_per_act < 0) & (pp.p < 0.05)).sum()
    print(f"Patients with negative slope: {n_neg}/{len(pp)} ({100*n_neg/len(pp):.1f}%)")
    print(f"Patients with neg slope & p<0.05: {n_neg_sig}/{len(pp)}")
    print(f"Median slope: {pp.slope_bg_per_act.median():.2f} mg/dL per activity-unit")
    print(f"Mean slope: {pp.slope_bg_per_act.mean():.2f} (SE {pp.slope_bg_per_act.sem():.2f})")

    # One-sample t-test against H0: slope=0
    t, p = stats.ttest_1samp(pp.slope_bg_per_act, 0.0)
    print(f"One-sample t-test (slope vs 0): t={t:.2f}, p={p:.3g}")
    # Sign test (binomial)
    from scipy.stats import binomtest
    bt = binomtest(n_neg, n=len(pp), p=0.5, alternative="greater")
    print(f"Sign test (P(neg) > 0.5): p={bt.pvalue:.3g}")

    print("\n=== By design ===")
    for d, sub in pp.groupby("design"):
        n_neg_d = (sub.slope_bg_per_act < 0).sum()
        print(f"  {d:14s}: n={len(sub)}, median slope {sub.slope_bg_per_act.median():+.2f}, "
              f"{n_neg_d}/{len(sub)} negative")

    out = {
        "scope": "within-patient validation of IOB-age framework at hypo",
        "n_patients_qualified": int(len(pp)),
        "n_negative_slope": int(n_neg),
        "n_negative_significant": int(n_neg_sig),
        "median_slope_bg_per_act_unit": float(pp.slope_bg_per_act.median()),
        "ttest_t": float(t), "ttest_p": float(p),
        "binomial_p": float(bt.pvalue),
        "per_patient": pp.to_dict(orient="records"),
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2954] {OUT}")


if __name__ == "__main__":
    main()
