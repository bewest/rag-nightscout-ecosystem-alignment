"""EXP-2965 - Per-patient validation of EXP-2961 sustained-high finding.

EXP-2961 reported pooled Loop_AB_ON +2.05 vs oref1 +0.98 at sustained-high.
This script repeats the EXP-2962 per-patient pattern at sustained-high windows,
and additionally decomposes per-patient slope into SMB-only and basal-only
channels (per EXP-2964 lesson).

Sustained-high entry: bg crosses above 200 mg/dL with no carbs in prior
120 min. Per-patient slope of ins_60 ~ vel_30 (and SMB-only, basal-only).

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
OUT = REPO / "externals" / "experiments" / "exp-2965_summary.json"

LOOP_AB_OFF = {"a", "f"}
LOOP_AB_ON = {"c", "d", "e", "g", "i"}
OREF0_PATS = {"odc-74077367", "odc-86025410", "odc-96254963"}

MIN_EVENTS = 15  # sustained-high events are rarer than PP


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
        ins_evt = sub["insulin_event"].values
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
                "patient_id": pid, "design": d,
                "bg_entry": float(bg[i]),
                "vel_30": vel,
                "ins_60_total": float(ins_evt[i:i + INS_WIN].sum()),
                "ins_60_bolus": float(bolus[i:i + INS_WIN].sum()),
                "ins_60_smb": float(smb[i:i + INS_WIN].sum()),
                "ins_60_basal_excess": float(basal_x[i:i + INS_WIN].sum()),
            })
            last_event_idx = i

    ev = pd.DataFrame(rows)
    print(f"Total sustained-high events: {len(ev):,}")
    if len(ev) == 0:
        return

    from scipy import stats
    from scipy.stats import binomtest

    print("\n=== Per-patient slopes (channels) ===")
    pp_rows = []
    for (pid, d), sub in ev.groupby(["patient_id", "design"]):
        if len(sub) < MIN_EVENTS:
            continue
        out = {"patient_id": pid, "design": d, "n": int(len(sub))}
        for label, col in [("total", "ins_60_total"),
                           ("smb", "ins_60_smb"),
                           ("basal_x", "ins_60_basal_excess"),
                           ("bolus", "ins_60_bolus")]:
            try:
                sl, _, _, p, se = stats.linregress(sub["vel_30"], sub[col])
                out[f"slope_{label}"] = float(sl)
                out[f"p_{label}"] = float(p)
            except Exception:
                out[f"slope_{label}"] = None
        pp_rows.append(out)
    pp = pd.DataFrame(pp_rows)
    print(f"Patients with >= {MIN_EVENTS} events: {len(pp)}")
    if len(pp):
        print(pp[["patient_id", "design", "n", "slope_total", "slope_smb",
                  "slope_basal_x", "slope_bolus"]].sort_values(
            ["design", "slope_total"]).to_string(index=False))

    print("\n=== Per-design summary (per-patient slope distribution) ===")
    summary = []
    for d, sub in pp.groupby("design"):
        row = {"design": d, "n_pat": int(len(sub))}
        for label in ("total", "smb", "basal_x", "bolus"):
            sl = sub[f"slope_{label}"].dropna().values
            if len(sl) == 0:
                continue
            n_pos = int((sl > 0).sum())
            n_neg = int((sl < 0).sum())
            bt = binomtest(n_pos, len(sl), p=0.5, alternative="two-sided") if len(sl) >= 1 else None
            row[f"{label}_median"] = float(np.median(sl))
            row[f"{label}_mean"] = float(np.mean(sl))
            row[f"{label}_npos"] = n_pos
            row[f"{label}_nneg"] = n_neg
            row[f"{label}_sign_p"] = float(bt.pvalue) if bt is not None else None
        summary.append(row)
        print(f"\n  {d} (n_pat={int(len(sub))})")
        for label in ("total", "smb", "basal_x", "bolus"):
            if f"{label}_median" not in row:
                continue
            print(f"    {label:>8}: median={row[f'{label}_median']:+.3f} "
                  f"mean={row[f'{label}_mean']:+.3f} "
                  f"({row[f'{label}_npos']}+/{row[f'{label}_nneg']}-) "
                  f"sign_p={row[f'{label}_sign_p']:.3g}")

    print("\n=== MWU Loop_AB_ON > oref1 (per channel) ===")
    mwu_out = {}
    for label in ("total", "smb", "basal_x", "bolus"):
        a = pp[pp.design == "Loop_AB_ON"][f"slope_{label}"].dropna().values
        b = pp[pp.design == "oref1"][f"slope_{label}"].dropna().values
        if len(a) >= 3 and len(b) >= 3:
            mw = stats.mannwhitneyu(a, b, alternative="greater")
            print(f"  {label:>8}: U={mw.statistic:.1f}  p(Loop_AB_ON>oref1)={mw.pvalue:.4g}  "
                  f"(Loop_AB_ON n={len(a)}, oref1 n={len(b)})")
            mwu_out[label] = {"U": float(mw.statistic), "p_one_sided": float(mw.pvalue),
                              "loop_ab_on_n": len(a), "oref1_n": len(b),
                              "loop_ab_on_slopes": sorted(a.round(3).tolist()),
                              "oref1_slopes": sorted(b.round(3).tolist())}
        else:
            print(f"  {label:>8}: TOO SMALL (Loop_AB_ON n={len(a)}, oref1 n={len(b)})")

    out = {
        "scope": "Per-patient validation of sustained-high velocity-coupling (EXP-2961)",
        "n_events": int(len(ev)),
        "min_events_per_patient": MIN_EVENTS,
        "per_patient": pp.to_dict(orient="records"),
        "per_design_summary": summary,
        "mwu": mwu_out,
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2965] {OUT}")


if __name__ == "__main__":
    main()
