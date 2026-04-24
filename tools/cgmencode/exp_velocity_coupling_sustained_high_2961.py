"""EXP-2961 - Velocity-vs-insulin coupling at sustained-high windows (no meal).

Tests whether the velocity-coupling observed at PP (EXP-2960) persists
OUTSIDE the meal context, isolating it as a controller property rather
than a meal-detection artefact.

Sustained-high entry: bg crosses above 200 mg/dL with no carbs in
prior 120 min. Same regression: ins_60 ~ vel_30, per-design.

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
OUT = REPO / "externals" / "experiments" / "exp-2961_summary.json"

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

    PRE_CARB = 24   # 120 min carb-isolation
    VEL_WIN = 6     # 30 min velocity window
    INS_WIN = 12    # 60 min insulin window
    THR = 200.0

    rows = []
    for pid, sub in g.groupby("patient_id"):
        d = design_of(pid, pid_to_lin.get(pid, ""))
        if d is None:
            continue
        sub = sub.sort_values("time").reset_index(drop=True)
        carbs = sub["carbs"].fillna(0).values
        carbs_pre = sub["carbs"].fillna(0).shift(1).rolling(PRE_CARB, min_periods=1).sum().fillna(0).values
        bg = sub["glucose"].values
        ins_evt = sub["insulin_event"].values
        bolus = sub["bolus"].fillna(0).values
        smb = sub["bolus_smb"].fillna(0).values
        basal_x = sub["basal_excess"].values
        n = len(sub)
        last_event_idx = -10**9
        for i in range(1, n - INS_WIN):
            # crossing above 200
            if not (bg[i - 1] < THR and bg[i] >= THR):
                continue
            if carbs_pre[i] != 0:
                continue
            if i - last_event_idx < INS_WIN:  # avoid overlapping windows
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
            ins_60 = float(ins_evt[i:i + INS_WIN].sum())
            ins_60_bolus = float(bolus[i:i + INS_WIN].sum())
            ins_60_smb = float(smb[i:i + INS_WIN].sum())
            ins_60_basalx = float(basal_x[i:i + INS_WIN].sum())
            rows.append({
                "patient_id": pid, "design": d,
                "bg_entry": float(bg[i]),
                "vel_30": vel,
                "ins_60_total": ins_60,
                "ins_60_bolus": ins_60_bolus,
                "ins_60_smb": ins_60_smb,
                "ins_60_basal_excess": ins_60_basalx,
            })
            last_event_idx = i

    ev = pd.DataFrame(rows)
    print(f"Total sustained-high events: {len(ev):,}")
    if len(ev) == 0:
        print("No events; aborting.")
        return

    print("\n=== By design (means) ===")
    print(ev.groupby("design").agg(
        n=("vel_30", "size"),
        n_pat=("patient_id", "nunique"),
        vel_mean=("vel_30", "mean"),
        ins_total=("ins_60_total", "mean"),
        ins_smb=("ins_60_smb", "mean"),
        ins_basal_x=("ins_60_basal_excess", "mean"),
        ins_bolus=("ins_60_bolus", "mean"),
    ).round(3).to_string())

    from scipy import stats
    print("\n=== Per-design regression: ins_60_total ~ vel_30 ===")
    out_rows = []
    for d, sub in ev.groupby("design"):
        if len(sub) < 30:
            print(f"\n  {d} (n={len(sub)}) — TOO SMALL, skipping regression")
            out_rows.append({"design": d, "n": int(len(sub)), "skipped": True})
            continue
        slope_s, intercept_s, r, p_s, se_s = stats.linregress(sub["vel_30"], sub["ins_60_total"])
        ci_lo_s = slope_s - 1.96 * se_s
        ci_hi_s = slope_s + 1.96 * se_s
        # Multi-factor controlling for bg_entry
        X = np.column_stack([sub["vel_30"], sub["bg_entry"], np.ones(len(sub))])
        y = sub["ins_60_total"].values
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        yhat = X @ beta
        resid = y - yhat
        rss = float(np.sum(resid ** 2))
        dof = max(len(sub) - X.shape[1], 1)
        sigma2 = rss / dof
        XtX_inv = np.linalg.pinv(X.T @ X)
        se_mf = float(np.sqrt(sigma2 * XtX_inv[0, 0]))
        slope_mf = float(beta[0])
        ci_lo_mf = slope_mf - 1.96 * se_mf
        ci_hi_mf = slope_mf + 1.96 * se_mf
        slope_smb, _, _, p_smb, se_smb = stats.linregress(sub["vel_30"], sub["ins_60_smb"])
        slope_bx, _, _, p_bx, se_bx = stats.linregress(sub["vel_30"], sub["ins_60_basal_excess"])
        print(f"\n  {d} (n={len(sub)}, n_pat={sub.patient_id.nunique()})")
        print(f"    Single   slope = {slope_s:+.4f} U per mg/dL/min  "
              f"95%CI [{ci_lo_s:+.4f},{ci_hi_s:+.4f}]  p={p_s:.3g}")
        print(f"    MultiFac slope = {slope_mf:+.4f} U per mg/dL/min  "
              f"95%CI [{ci_lo_mf:+.4f},{ci_hi_mf:+.4f}]  (controls bg_entry)")
        print(f"    SMB-only slope = {slope_smb:+.4f}  p={p_smb:.3g}   "
              f"basal_excess slope = {slope_bx:+.4f}  p={p_bx:.3g}")
        out_rows.append({
            "design": d, "n": int(len(sub)), "n_pat": int(sub.patient_id.nunique()),
            "single_slope": slope_s, "single_se": se_s,
            "single_ci_lo": ci_lo_s, "single_ci_hi": ci_hi_s, "single_p": p_s,
            "mf_slope": slope_mf, "mf_se": se_mf,
            "mf_ci_lo": ci_lo_mf, "mf_ci_hi": ci_hi_mf,
            "smb_slope": slope_smb, "smb_p": p_smb,
            "basal_excess_slope": slope_bx, "basal_excess_p": p_bx,
        })

    out = {
        "scope": "Velocity-vs-insulin coupling at sustained-high (no meal)",
        "n_events": int(len(ev)),
        "by_design_means": ev.groupby("design").agg(
            n=("vel_30", "size"),
            n_pat=("patient_id", "nunique"),
            vel_mean=("vel_30", "mean"),
            ins_total=("ins_60_total", "mean"),
            ins_smb=("ins_60_smb", "mean"),
            ins_basal_x=("ins_60_basal_excess", "mean"),
        ).reset_index().to_dict(orient="records"),
        "per_design_regression": out_rows,
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2961] {OUT}")


if __name__ == "__main__":
    main()
