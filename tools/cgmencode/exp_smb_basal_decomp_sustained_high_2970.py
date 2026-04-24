"""EXP-2970 - SMB-vs-basal decomposition at sustained-high.

Combines EXP-2964 decomposition pattern with EXP-2961 sustained-high
window definition. For each design, fit per-channel velocity-coupling
slope at sustained-high entries, with 95% CI and per-patient breakdown.

Tests whether Loop_AB_ON's autobolus-on policy is more aggressive at
sustained-high than oref1's SMB triggering policy.

Scope: AID-author audience.
What this is NOT: per-patient therapy advice.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
SIMP = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = REPO / "externals" / "experiments" / "exp-2970_summary.json"

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
    g["basal_excess"] = ((g["actual_basal_rate"].fillna(0) -
                          g["scheduled_basal_rate"].fillna(0)) * 5.0 / 60.0).clip(lower=0)

    PRE_CARB = 24
    VEL_WIN = 6
    INS_WIN = 12
    THR = 200.0

    rows = []
    for pid, sub in g.groupby("patient_id"):
        d = design_of(pid, pid_to_lin.get(pid, ""))
        if d is None:
            continue
        sub = sub.sort_values("time").reset_index(drop=True)
        carbs_pre = sub["carbs"].fillna(0).shift(1).rolling(PRE_CARB, min_periods=1).sum().fillna(0).values
        bg = sub["glucose"].values
        bolus = sub["bolus"].fillna(0).values
        smb = sub["bolus_smb"].fillna(0).values
        basal_x = sub["basal_excess"].values
        n = len(sub)
        last_event_idx = -10**9
        for i in range(1, n - INS_WIN):
            if not (bg[i - 1] < THR and bg[i] >= THR):
                continue
            if carbs_pre[i] != 0:
                continue
            if i - last_event_idx < INS_WIN:
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
            rows.append({
                "patient_id": pid, "design": d, "vel_30": vel,
                "ins_60_bolus": float(bolus[i:i + INS_WIN].sum()),
                "ins_60_smb": float(smb[i:i + INS_WIN].sum()),
                "ins_60_basal_excess": float(basal_x[i:i + INS_WIN].sum()),
            })
            last_event_idx = i

    ev = pd.DataFrame(rows)
    ev["ins_60_total"] = ev["ins_60_bolus"] + ev["ins_60_smb"] + ev["ins_60_basal_excess"]
    print(f"Total sustained-high events: {len(ev):,}")
    if len(ev) == 0:
        return

    print("\n=== Component MEANS at sustained-high ===")
    comp = ev.groupby("design").agg(
        n=("vel_30", "size"),
        n_pat=("patient_id", "nunique"),
        bolus=("ins_60_bolus", "mean"),
        smb=("ins_60_smb", "mean"),
        basal_x=("ins_60_basal_excess", "mean"),
        total=("ins_60_total", "mean"),
    )
    print(comp.round(3).to_string())

    from scipy import stats
    from scipy.stats import binomtest

    print("\n=== Per-design pooled velocity-coupling slopes (per channel) ===")
    pooled = []
    for d, sub in ev.groupby("design"):
        if len(sub) < 30:
            print(f"  {d}: n={len(sub)} TOO SMALL")
            continue
        comps = {}
        for label, col in [("bolus", "ins_60_bolus"),
                           ("smb", "ins_60_smb"),
                           ("basal_excess", "ins_60_basal_excess"),
                           ("total", "ins_60_total")]:
            sl, _, _, p, se = stats.linregress(sub["vel_30"], sub[col])
            comps[label] = {"slope": float(sl), "se": float(se),
                            "ci_lo": float(sl - 1.96 * se),
                            "ci_hi": float(sl + 1.96 * se),
                            "p": float(p)}
        print(f"\n  {d} (n={len(sub)}, n_pat={sub.patient_id.nunique()})")
        for label in ("bolus", "smb", "basal_excess", "total"):
            c = comps[label]
            print(f"    {label:>14}: {c['slope']:+.4f}  "
                  f"95%CI [{c['ci_lo']:+.4f},{c['ci_hi']:+.4f}]  p={c['p']:.3g}")
        pooled.append({"design": d, "n": int(len(sub)),
                       "n_pat": int(sub.patient_id.nunique()),
                       "components": comps})

    print("\n=== Per-patient SMB-channel slopes at sustained-high ===")
    pp_rows = []
    for (pid, d), sub in ev.groupby(["patient_id", "design"]):
        if len(sub) < 10:
            continue
        out = {"patient_id": pid, "design": d, "n": int(len(sub))}
        for label, col in [("smb", "ins_60_smb"),
                           ("basal_x", "ins_60_basal_excess"),
                           ("bolus", "ins_60_bolus"),
                           ("total", "ins_60_total")]:
            try:
                sl, _, _, p, se = stats.linregress(sub["vel_30"], sub[col])
                out[f"slope_{label}"] = float(sl)
            except Exception:
                out[f"slope_{label}"] = None
        pp_rows.append(out)
    pp = pd.DataFrame(pp_rows)
    if len(pp):
        print(pp[["patient_id", "design", "n", "slope_smb", "slope_basal_x", "slope_total"]]
              .sort_values(["design", "slope_smb"]).to_string(index=False))

    print("\n=== Per-design summary of per-patient SMB slopes ===")
    pp_summary = []
    for d, sub in pp.groupby("design"):
        sl = sub["slope_smb"].dropna().values
        if len(sl) == 0:
            continue
        n_pos = int((sl > 0).sum())
        n_neg = int((sl < 0).sum())
        bt = binomtest(n_pos, len(sl), p=0.5, alternative="two-sided") if len(sl) >= 1 else None
        print(f"  {d} (n_pat={len(sl)}) median={np.median(sl):+.4f} "
              f"mean={np.mean(sl):+.4f} ({n_pos}+/{n_neg}-)")
        pp_summary.append({"design": d, "n_pat": int(len(sl)),
                           "smb_median": float(np.median(sl)),
                           "smb_mean": float(np.mean(sl)),
                           "n_pos": n_pos, "n_neg": n_neg,
                           "sign_p": float(bt.pvalue) if bt else None})

    mwu_out = {}
    print("\n=== MWU per-patient SMB-slope (two-sided) ===")
    for (a_d, b_d) in [("Loop_AB_ON", "oref1")]:
        a = pp[pp.design == a_d]["slope_smb"].dropna().values
        b = pp[pp.design == b_d]["slope_smb"].dropna().values
        if len(a) >= 2 and len(b) >= 2:
            mw = stats.mannwhitneyu(a, b, alternative="two-sided")
            print(f"  {a_d} vs {b_d}: U={mw.statistic:.1f} p={mw.pvalue:.4g}")
            print(f"    {a_d} slopes: {sorted(a.round(3).tolist())}")
            print(f"    {b_d} slopes: {sorted(b.round(3).tolist())}")
            mwu_out[f"{a_d}_vs_{b_d}"] = {"U": float(mw.statistic),
                                          "p_two_sided": float(mw.pvalue)}

    out = {
        "scope": "SMB-vs-basal decomposition at sustained-high (no meal)",
        "n_events": int(len(ev)),
        "component_means": comp.reset_index().round(3).to_dict(orient="records"),
        "pooled_per_channel_slopes": pooled,
        "per_patient_smb": pp.to_dict(orient="records"),
        "per_design_pp_summary": pp_summary,
        "mwu_pp_smb": mwu_out,
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2970] {OUT}")


if __name__ == "__main__":
    main()
