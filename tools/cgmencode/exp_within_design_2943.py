"""EXP-2943 - per-patient recovery scatter against patient-level covariates.

If selection-bias drives the recovery gap, within-design variance should
be large and patient-level covariates (TDD/kg proxy, BG variability,
mean basal demand) should explain a substantial fraction.

Reuse EXP-2942 carb-isolated event extraction.

Scope: AID-author audience. Within-design heterogeneity diagnostic.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
SIMP = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = REPO / "externals" / "experiments" / "exp-2943_summary.json"

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

    g = pd.read_parquet(GRID, columns=["patient_id", "time", "glucose", "carbs", "bolus_smb"])
    g = g[g.patient_id.isin(set(simp.patient_id))].dropna(subset=["glucose"])
    g = g.sort_values(["patient_id", "time"]).reset_index(drop=True)

    # Per-patient covariates from full grid
    cov_rows = []
    for pid, sub in g.groupby("patient_id"):
        d = design_of(pid, pid_to_lin.get(pid, ""))
        if d is None:
            continue
        bg = sub["glucose"].dropna()
        smb = sub["bolus_smb"].fillna(0)
        carbs = sub["carbs"].fillna(0)
        days = (sub["time"].max() - sub["time"].min()).total_seconds() / 86400
        cov_rows.append({
            "patient_id": pid, "design": d,
            "bg_mean": float(bg.mean()),
            "bg_cv": float(bg.std() / bg.mean()),
            "bg_pct_high": float((bg > 180).mean()),
            "bg_pct_low": float((bg < 70).mean()),
            "smb_per_day": float(smb[smb > 0].count() / max(days, 1)),
            "smb_total_per_day": float(smb.sum() / max(days, 1)),
            "carbs_per_day": float(carbs.sum() / max(days, 1)),
            "days": days,
        })
    cov = pd.DataFrame(cov_rows)

    # Recovery extraction (EXP-2942 method)
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
        ents = sub[(sub["glucose"] > HIGH) & (bg_prev <= HIGH) & (bg_max_30 <= HIGH) & (carbs_60 == 0)]
        events = []
        for ent_idx in ents.index:
            win = sub.iloc[ent_idx:ent_idx + n_cells]
            if len(win) < n_cells or win["carbs"].fillna(0).sum() > 0:
                continue
            events.append(bool(win["glucose"].iloc[-1] < HIGH))
        if len(events) >= 5:
            rec_rows.append({"patient_id": pid, "design": d,
                             "n_events": len(events), "recovered": float(np.mean(events))})

    rec = pd.DataFrame(rec_rows)
    df = rec.merge(cov, on=["patient_id", "design"])
    print(f"Patients: {len(df)}")
    print(df.sort_values(["design", "recovered"])[
        ["patient_id", "design", "n_events", "recovered", "bg_mean", "bg_cv", "smb_per_day", "smb_total_per_day"]
    ].to_string(index=False))

    print("\n=== Within-design variance ===")
    wd = df.groupby("design")["recovered"].agg(["mean", "std", "min", "max"]).round(3)
    print(wd.to_string())

    print("\n=== Between- vs within-design variance ===")
    grand = df["recovered"].mean()
    ss_total = ((df["recovered"] - grand) ** 2).sum()
    means = df.groupby("design")["recovered"].transform("mean")
    ss_between = ((means - grand) ** 2).sum()
    ss_within = ((df["recovered"] - means) ** 2).sum()
    eta_sq = ss_between / ss_total
    print(f"  SS_total:    {ss_total:.4f}")
    print(f"  SS_between:  {ss_between:.4f}  ({ss_between/ss_total*100:.1f}%)")
    print(f"  SS_within:   {ss_within:.4f}  ({ss_within/ss_total*100:.1f}%)")
    print(f"  eta-squared: {eta_sq:.3f}  (>0.5 = design dominates; <0.3 = patient dominates)")

    print("\n=== Spearman ρ(recovered, covariate) within each design ===")
    cov_cols = ["bg_mean", "bg_cv", "bg_pct_high", "bg_pct_low",
                "smb_per_day", "smb_total_per_day", "carbs_per_day"]
    cor_table = []
    for d, sub in df.groupby("design"):
        if len(sub) < 3:
            continue
        for c in cov_cols:
            rho = sub[["recovered", c]].corr(method="spearman").iloc[0, 1]
            cor_table.append({"design": d, "cov": c, "rho": float(rho), "n": len(sub)})
    cor_df = pd.DataFrame(cor_table)
    print(cor_df.pivot(index="cov", columns="design", values="rho").round(2).to_string())

    out = {
        "scope": "within-design vs between-design variance + per-patient covariates",
        "n_patients": int(len(df)),
        "eta_squared_design": float(eta_sq),
        "by_design": wd.reset_index().to_dict(orient="records"),
        "patients": df.to_dict(orient="records"),
        "correlations": cor_table,
        "verdict": "DESIGN-DOMINATED" if eta_sq > 0.5 else ("PATIENT-DOMINATED" if eta_sq < 0.3 else "MIXED"),
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2943] verdict: {out['verdict']}")


if __name__ == "__main__":
    main()
