"""EXP-2953 - Uniform action-curve re-derivation of IOB-age at HYPO descent.

Companion to EXP-2950 (sustained-high). Applies the SAME uniform
biexponential action curve (peak 75 min, DIA 300 min) to event history
(bolus + bolus_smb + basal_excess) at HYPO descent anchors.

EXP-2947 found: Loop_AB_ON has LESS iob_at_entry, MORE prior decay,
MORE basal cuts — yet 2x severe-hypo rate. Mechanism interpretation:
fresh IOB (recently delivered, near peak action) drives BG down;
stale IOB is buffer.

This experiment tests with uniform synth: at hypo descent entry,
oref1 should have LOWER activity-per-IOB ratio (staler) than
Loop_AB_ON, and similar or HIGHER total iob (the buffer).

Anchor: BG crosses 80 falling, prior 30min all >80, no carbs ±60min.

Scope: AID-author audience. NOT therapy advice.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
SIMP = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = REPO / "externals" / "experiments" / "exp-2953_summary.json"

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


# ---------- Uniform biexponential action curve ----------
# IOB(t) = U_total * (1 - F(t)) where F is fraction absorbed
# Activity(t) = U_total * f(t) where f is action density
# Use bilinear approximation: peak at 75 min, DIA 300 min
# IOB curve: 1.0 at t=0, decays per simple bilinear

PEAK_MIN = 75.0
DIA_MIN = 300.0


def iob_remaining(elapsed_min):
    """Fraction of insulin still on board at elapsed_min after delivery."""
    t = np.asarray(elapsed_min, dtype=float)
    out = np.ones_like(t)
    # Before peak: 1 - 0.5*(t/peak)^2  (cumulative absorbed=0.5 at peak)
    pre = t < PEAK_MIN
    out_pre = 1.0 - 0.5 * (t[pre] / PEAK_MIN) ** 2
    # After peak through DIA: linear decay from 0.5 to 0
    post = (t >= PEAK_MIN) & (t < DIA_MIN)
    out_post = 0.5 * (1.0 - (t[post] - PEAK_MIN) / (DIA_MIN - PEAK_MIN))
    # Beyond DIA: 0
    out[pre] = out_pre
    out[post] = out_post
    out[t >= DIA_MIN] = 0.0
    return out


def activity_density(elapsed_min):
    """Fraction of total insulin acting per minute at elapsed_min."""
    t = np.asarray(elapsed_min, dtype=float)
    out = np.zeros_like(t)
    pre = t < PEAK_MIN
    out[pre] = (t[pre] / PEAK_MIN) / PEAK_MIN  # rises linearly to 1/PEAK at peak (after derivative)
    # Derivative of -(1-0.5*(t/p)^2) is t/p^2
    out[pre] = t[pre] / (PEAK_MIN ** 2)
    post = (t >= PEAK_MIN) & (t < DIA_MIN)
    # Derivative of 0.5*(1-(t-peak)/(DIA-peak)) wrt t is -0.5/(DIA-peak), magnitude is the |rate|
    out[post] = 0.5 / (DIA_MIN - PEAK_MIN)
    out[t >= DIA_MIN] = 0.0
    return out


def synth_iob_at(events_t_min, events_u, eval_t_min):
    """Compute synthetic IOB at eval_t_min from prior events.

    events_t_min: sorted ascending (relative minutes); events_u: insulin units.
    eval_t_min: scalar (minutes, must be >= max events_t_min for past events).
    """
    if len(events_t_min) == 0:
        return 0.0, 0.0
    elapsed = eval_t_min - events_t_min
    elapsed = elapsed[elapsed >= 0]
    units = events_u[:len(elapsed)]
    iob = float(np.sum(units * iob_remaining(elapsed)))
    act = float(np.sum(units * activity_density(elapsed)))
    return iob, act


def main():
    simp = pd.read_parquet(SIMP, columns=["patient_id", "lineage"]).drop_duplicates("patient_id")
    pid_to_lin = dict(zip(simp.patient_id, simp.lineage))

    cols = ["patient_id", "time", "glucose", "carbs", "bolus", "bolus_smb",
            "actual_basal_rate", "scheduled_basal_rate"]
    g = pd.read_parquet(GRID, columns=cols)
    g = g[g.patient_id.isin(set(simp.patient_id))].dropna(subset=["glucose"])
    g = g.sort_values(["patient_id", "time"]).reset_index(drop=True)
    g["bolus_total"] = g["bolus"].fillna(0) + g["bolus_smb"].fillna(0)
    # Per-5min basal delivery DEVIATION from schedule (units): clamp to >= 0
    # 5min duration -> rate per hour * 5/60 = U
    g["basal_excess"] = (g["actual_basal_rate"].fillna(0) -
                         g["scheduled_basal_rate"].fillna(0)) * 5.0 / 60.0
    g["basal_excess"] = g["basal_excess"].clip(lower=0)
    # Insulin event total (treat as point delivered at start of 5min cell)
    g["insulin_event"] = g["bolus_total"] + g["basal_excess"]

    rows = []
    LOOKBACK_MIN = int(DIA_MIN)
    LOOKBACK_CELLS = LOOKBACK_MIN // 5

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
            # HYPO descent: BG crosses 80 falling, prior 30min >80, carb-isolated ±60min
            if not (bg[i] <= 80 and bg_prev[i] > 80 and bg_min_30[i] > 80
                    and carbs_60_pre[i] == 0
                    and sub.iloc[i:i+12]["carbs"].fillna(0).sum() == 0):
                continue
            # Build event history relative to entry time
            past_idx = np.arange(i - LOOKBACK_CELLS, i + 1)
            past_evt_u = ins_evt[past_idx]
            mask = past_evt_u > 1e-4
            if not mask.any():
                evt_t = np.array([])
                evt_u = np.array([])
            else:
                # times relative to event entry (i): cell j is (i-j) cells before = (i-j)*5 min
                rel_min = (i - past_idx[mask]) * 5.0  # positive = past
                # convert to "time of event" in minute scale where eval_t = 0
                evt_t = -rel_min  # negative relative times
                evt_u = past_evt_u[mask]
            # eval at entry (t=0): elapsed = 0 - evt_t = rel_min (positive)
            iob_entry, act_entry = synth_iob_at(evt_t, evt_u, 0.0)
            # eval at +60min (window end)
            i_end = i + 12
            past_idx2 = np.arange(i_end - LOOKBACK_CELLS, i_end + 1)
            past_idx2 = past_idx2[past_idx2 >= 0]
            past_evt_u2 = ins_evt[past_idx2]
            mask2 = past_evt_u2 > 1e-4
            if mask2.any():
                rel_min2 = (i_end - past_idx2[mask2]) * 5.0
                evt_t2 = -rel_min2
                evt_u2 = past_evt_u2[mask2]
            else:
                evt_t2 = np.array([])
                evt_u2 = np.array([])
            iob_end, act_end = synth_iob_at(evt_t2, evt_u2, 0.0)

            rows.append({
                "patient_id": pid, "design": d,
                "synth_iob_entry": iob_entry,
                "synth_act_entry": act_entry,
                "synth_freshness": (act_entry / iob_entry) if iob_entry > 1e-3 else np.nan,
                "synth_iob_end": iob_end,
                "synth_act_end": act_end,
                "synth_iob_delta": iob_end - iob_entry,
                "synth_act_delta": act_end - act_entry,
                "bg_entry": float(bg[i]),
                "bg_min_60": float(sub.iloc[i:i+12]["glucose"].min()),
                "tbr_70_pct": float((sub.iloc[i:i+12]["glucose"] < 70).mean()),
                "tbr_54_pct": float((sub.iloc[i:i+12]["glucose"] < 54).mean()),
            })

    ev = pd.DataFrame(rows)
    print(f"Total sustained-high carb-isolated events: {len(ev):,}\n")

    summary = ev.groupby("design").agg(
        n=("synth_iob_entry", "size"),
        iob_entry=("synth_iob_entry", "mean"),
        act_entry=("synth_act_entry", "mean"),
        freshness=("synth_freshness", "mean"),
        iob_delta=("synth_iob_delta", "mean"),
        bg_min_60=("bg_min_60", "mean"),
        tbr_70_pct=("tbr_70_pct", "mean"),
        tbr_54_pct=("tbr_54_pct", "mean"),
    ).round(4)
    print("=== Per design (uniform biexponential, hypo descent) ===")
    print(summary.to_string())

    print("\n=== Loop_AB_ON vs oref1 contrasts ===")
    for col in ["synth_iob_entry", "synth_act_entry", "synth_freshness",
                "synth_iob_delta", "bg_min_60", "tbr_54_pct"]:
        a = ev[ev.design == "Loop_AB_ON"][col].dropna().values
        b = ev[ev.design == "oref1"][col].dropna().values
        if len(a) > 5 and len(b) > 5:
            from scipy import stats
            u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
            print(f"  {col:22s}: Loop {a.mean():+.4f} | oref1 {b.mean():+.4f} "
                  f"| Δ {a.mean()-b.mean():+.4f} (MW p={p:.3g})")

    out = {
        "scope": "uniform action-curve re-derivation of IOB-age mechanism",
        "curve": {"peak_min": PEAK_MIN, "dia_min": DIA_MIN, "form": "bilinear"},
        "n_events": int(len(ev)),
        "by_design": summary.reset_index().to_dict(orient="records"),
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2953] {OUT}")


if __name__ == "__main__":
    main()
