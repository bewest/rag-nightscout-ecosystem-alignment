"""EXP-2972 - Trigger frequency vs per-event magnitude decomposition.

In the 70-100 no-carb sweet spot, decompose total SMB delivery into:
  emission_rate = P(bolus_smb > 0)
  mean_emission = E[bolus_smb | bolus_smb > 0]
Total per-cell SMB = emission_rate * mean_emission.

Hypothesis: Loop_AB_ON has higher emission_rate (more frequent
triggers) at near-equal mean_emission. That would be the precise
AID-author lever (cycle frequency / SMB cap policy).

Reports per-design pooled and per-patient.

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
OUT = REPO / "externals" / "experiments" / "exp-2972_summary.json"

LOOP_AB_OFF = {"a", "f"}
LOOP_AB_ON = {"c", "d", "e", "g", "i"}
OREF0_PATS = {"odc-74077367", "odc-86025410", "odc-96254963"}

BAND_LO, BAND_HI = 70.0, 100.0
PRE_NO_CARB = 24  # 120 min


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

    cols = ["patient_id", "time", "glucose", "carbs", "bolus_smb"]
    g = pd.read_parquet(GRID, columns=cols)
    g = g[g.patient_id.isin(set(simp.patient_id))].dropna(subset=["glucose"])
    g = g.sort_values(["patient_id", "time"]).reset_index(drop=True)

    cells = []  # one row per qualifying 5-min cell
    for pid, sub in g.groupby("patient_id"):
        d = design_of(pid, pid_to_lin.get(pid, ""))
        if d is None:
            continue
        sub = sub.sort_values("time").reset_index(drop=True)
        carbs = sub["carbs"].fillna(0).values
        carbs_pre = sub["carbs"].fillna(0).shift(1).rolling(PRE_NO_CARB, min_periods=1).sum().fillna(0).values
        bg = sub["glucose"].values
        smb = sub["bolus_smb"].fillna(0).values
        n = len(sub)
        mask = (
            (~np.isnan(bg))
            & (bg >= BAND_LO) & (bg < BAND_HI)
            & (carbs_pre == 0) & (carbs == 0)
        )
        idx = np.where(mask)[0]
        for i in idx:
            cells.append({"patient_id": pid, "design": d,
                          "smb": float(smb[i]),
                          "fired": int(smb[i] > 0)})

    df = pd.DataFrame(cells)
    print(f"Total qualifying cells: {len(df):,}")

    print("\n=== Pooled per-design decomposition (70-100 no-carb) ===")
    pooled = []
    for d, sub in df.groupby("design"):
        n = len(sub)
        n_fired = int(sub["fired"].sum())
        em_rate = n_fired / n if n else 0.0
        mean_em = float(sub.loc[sub.fired == 1, "smb"].mean()) if n_fired else 0.0
        mean_total = float(sub["smb"].mean())
        # Wilson 95% CI for emission rate
        if n >= 30:
            z = 1.96
            p = em_rate
            denom = 1 + z * z / n
            center = (p + z * z / (2 * n)) / denom
            half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
            ci_lo, ci_hi = center - half, center + half
        else:
            ci_lo = ci_hi = float("nan")
        print(f"  {d:>12} n={n:>7} fired={n_fired:>6} "
              f"em_rate={em_rate:.4f} [{ci_lo:.4f},{ci_hi:.4f}] "
              f"mean_em={mean_em:.4f}U mean_total/cell={mean_total:.5f}U")
        pooled.append({"design": d, "n_cells": n, "n_fired": n_fired,
                       "emission_rate": em_rate,
                       "emission_rate_ci_lo": float(ci_lo),
                       "emission_rate_ci_hi": float(ci_hi),
                       "mean_emission_U": mean_em,
                       "mean_smb_per_cell_U": mean_total})

    print("\n=== Per-patient decomposition ===")
    pp_rows = []
    for (pid, d), sub in df.groupby(["patient_id", "design"]):
        n = len(sub)
        if n < 30:
            continue
        n_fired = int(sub["fired"].sum())
        em_rate = n_fired / n if n else 0.0
        mean_em = float(sub.loc[sub.fired == 1, "smb"].mean()) if n_fired else 0.0
        pp_rows.append({"patient_id": pid, "design": d, "n_cells": n,
                        "n_fired": n_fired,
                        "emission_rate": em_rate,
                        "mean_emission_U": mean_em,
                        "mean_smb_per_cell_U": float(sub["smb"].mean())})
    pp = pd.DataFrame(pp_rows)
    if len(pp):
        print(pp.sort_values(["design", "emission_rate"]).to_string(index=False))

    from scipy import stats
    print("\n=== Per-design summary across patients ===")
    pp_sum = []
    for d, sub in pp.groupby("design"):
        if len(sub) == 0:
            continue
        rates = sub["emission_rate"].values
        means = sub["mean_emission_U"].values
        print(f"  {d} (n_pat={len(sub)}) "
              f"em_rate median={np.median(rates):.4f} mean={np.mean(rates):.4f} | "
              f"mean_em median={np.median(means):.4f} mean={np.mean(means):.4f}")
        pp_sum.append({"design": d, "n_pat": int(len(sub)),
                       "em_rate_median": float(np.median(rates)),
                       "em_rate_mean": float(np.mean(rates)),
                       "mean_em_median": float(np.median(means)),
                       "mean_em_mean": float(np.mean(means))})

    mwu_out = {}
    for (a_d, b_d) in [("Loop_AB_ON", "oref1")]:
        for col in ["emission_rate", "mean_emission_U"]:
            a = pp[pp.design == a_d][col].values
            b = pp[pp.design == b_d][col].values
            if len(a) >= 3 and len(b) >= 3:
                mw = stats.mannwhitneyu(a, b, alternative="two-sided")
                print(f"  MWU {a_d} vs {b_d} on {col}: U={mw.statistic:.1f} p={mw.pvalue:.4g}")
                mwu_out[f"{a_d}_vs_{b_d}__{col}"] = {
                    "U": float(mw.statistic), "p_two_sided": float(mw.pvalue),
                    "a_n": len(a), "b_n": len(b)}

    out = {
        "scope": "Trigger frequency vs per-event magnitude decomposition at 70-100 no-carb",
        "band": [BAND_LO, BAND_HI],
        "pooled": pooled,
        "per_patient": pp.to_dict(orient="records"),
        "per_design_summary": pp_sum,
        "mwu": mwu_out,
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2972] {OUT}")


if __name__ == "__main__":
    main()
